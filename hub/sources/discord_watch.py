"""Read-only Discord Gateway worker. Run with the project's discord.py environment."""
import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
import discord
from ..core import Store, now, require
from .discord_bot import normalize, DiscordBot
from .discord_stream import Queue, process


def observation(m, application):
    raw={'id':str(m.id),'channel_id':str(m.channel.id),'timestamp':m.created_at.isoformat(),
         'edited_timestamp':m.edited_at.isoformat() if m.edited_at else None,'content':m.content,
         'author':{'id':str(m.author.id),'username':m.author.name,'global_name':m.author.global_name},
         'attachments':[{'id':str(a.id),'filename':a.filename,'size':a.size,'content_type':a.content_type} for a in m.attachments]}
    if m.reference and m.reference.message_id:
        raw['message_reference']={'message_id':str(m.reference.message_id),'channel_id':str(m.reference.channel_id),
                                  'guild_id':str(m.reference.guild_id)}
    return normalize(raw,application,str(m.guild.id),str(m.channel.id),thread=isinstance(m.channel,discord.Thread))


class Collector(discord.Client):
    def __init__(self, config, root):
        intents=discord.Intents.none();intents.guilds=True;intents.guild_messages=True;intents.message_content=True
        super().__init__(intents=intents,max_messages=None,chunk_guilds_at_startup=False)
        self.config=config;self.root=root;self.dbpath=root/'discord-live.sqlite'
        self.store=Store(self.dbpath);self.dbpath.chmod(0o600)
        self.queue=Queue(self.store.db,config['guildAllowlist'])
        self.allowed={int(x) for x in config['guildAllowlist']}
        self.started=time.time();self.metrics={'processed':0,'apiCalls':0,'retained':0,'duplicates':0,'errors':0,'evidenceGaps':0,'readyCount':0,'resumeCount':0,'disconnectCount':0}
        self.tasks=[];self.connected=False;self.reconcile_now=asyncio.Event();self._storage_closed=False

    def status(self):
        if self._storage_closed:return
        report={'updated':now(),'connected':self.connected,'uptimeSeconds':round(time.time()-self.started),
                'guildsConnected':sum(g.id in self.allowed for g in self.guilds),
                'queueDepth':self.store.db.execute('SELECT COUNT(*) FROM discord_queue').fetchone()[0],
                'coverage':dict(self.store.db.execute('SELECT state,COUNT(*) FROM discord_coverage GROUP BY state').fetchall()),
                'gapCount':self.store.db.execute('SELECT COUNT(*) FROM discord_gaps').fetchone()[0],
                'metrics':self.metrics,'initialHistoryEnabled':self.config.get('initialHistoryEnabled',False)}
        path=self.root/'discord-status.json';temporary=path.with_suffix('.tmp')
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:json.dump(report,f,indent=2)
        temporary.replace(path)

    async def setup_hook(self):
        require(str(self.application_id)==self.config['applicationId'],'wrong application')
        self.tasks=[asyncio.create_task(self.consume()),asyncio.create_task(self.reconcile()),asyncio.create_task(self.heartbeat())]

    async def on_ready(self):
        self.metrics['readyCount']+=1;self.connected=True;self.reconcile_now.set();self.status()

    async def on_resumed(self):
        self.metrics['resumeCount']+=1;self.connected=True;self.reconcile_now.set();self.status()

    async def on_disconnect(self):
        self.metrics['disconnectCount']+=1;self.connected=False;self.status()

    async def on_error(self,event,*args,**kwargs):
        self.metrics['errors']+=1 # Never dump event content or exception payloads.
        self.status()

    def add(self,guild,channel,message,kind='fetch'):
        with self.store.db:self.queue.enqueue(guild,channel,message,kind)

    async def on_message(self,m):
        if m.guild and m.guild.id in self.allowed:self.add(m.guild.id,m.channel.id,m.id)

    async def on_raw_message_edit(self,event):
        if event.guild_id in self.allowed:self.add(event.guild_id,event.channel_id,event.message_id)

    async def on_raw_message_delete(self,event):
        if event.guild_id in self.allowed:self.add(event.guild_id,event.channel_id,event.message_id,'delete')

    async def on_raw_bulk_message_delete(self,event):
        if event.guild_id in self.allowed:
            for mid in event.message_ids:self.add(event.guild_id,event.channel_id,mid,'delete')

    async def on_thread_create(self,thread):
        if thread.guild.id in self.allowed:self.reconcile_now.set()

    async def on_guild_channel_create(self,channel):
        if channel.guild.id in self.allowed:self.reconcile_now.set()

    async def heartbeat(self):
        while not self.is_closed():
            self.status();await asyncio.sleep(10)

    async def consume(self):
        await self.wait_until_ready()
        while not self.is_closed():
            item=self.queue.next()
            if not item:await asyncio.sleep(.5);continue
            try:
                current=None;context=[]
                if item['kind']!='delete':
                    channel=self.get_channel(int(item['channel'])) or await self.fetch_channel(int(item['channel']))
                    require(channel.guild.id==int(item['guild']) and channel.guild.id in self.allowed,'channel scope changed')
                    m=await channel.fetch_message(int(item['message']))
                    current=observation(m,self.config['applicationId'])
                    # Bounded contextual reads, no AI channel scanning. Unrelated text is never persisted.
                    async for older in channel.history(limit=4,before=m,after=m.created_at-timedelta(minutes=10)):
                        context.append(observation(older,self.config['applicationId']))
                    context.reverse()
                    if m.reference and m.reference.message_id and m.reference.channel_id==m.channel.id and all(x['originId']!=str(m.reference.message_id) for x in context):
                        try:
                            reply=await channel.fetch_message(m.reference.message_id)
                            if reply.created_at>=datetime.now(timezone.utc)-timedelta(days=30):
                                context.append(observation(reply,self.config['applicationId']))
                        except discord.HTTPException:pass # Reported by evidenceGaps; never claim complete.
                result=await asyncio.to_thread(process,self.dbpath,self.config,item,current,context)
                self.metrics['processed']+=1;self.metrics['apiCalls']+=result.get('apiCalls',0)
                self.metrics['retained']+=result.get('retained',0);self.metrics['duplicates']+=result.get('duplicate',0)
                self.metrics['evidenceGaps']+=result.get('evidenceGapCount',0)
            except discord.NotFound:
                with self.store.db:
                    self.queue.gap(item['channel'],item['message'],'unavailable-not-explicit-deletion');self.queue.ack(item)
            except Exception as error:
                self.metrics['errors']+=1
                self.queue.fail(item,type(error).__name__)
            self.status()

    async def reconcile(self):
        await self.wait_until_ready()
        while not self.is_closed():
            self.reconcile_now.clear()
            try:
                for guild in self.guilds:
                    if guild.id not in self.allowed:continue
                    targets={c.id:c for c in guild.channels if isinstance(c,(discord.TextChannel,discord.VoiceChannel,discord.StageChannel))}
                    for thread in await guild.active_threads():targets[thread.id]=thread
                    # Archived enumeration is bounded per pass and explicitly not counted as complete.
                    if self.config.get('initialHistoryEnabled',False):
                        for channel in guild.channels:
                            if isinstance(channel,(discord.TextChannel,discord.ForumChannel)):
                                try:
                                    async for thread in channel.archived_threads(limit=100):targets[thread.id]=thread
                                except discord.HTTPException:
                                    with self.store.db:self.queue.gap(channel.id,'0','archived-thread-access')
                    for channel in targets.values():
                        if not channel.permissions_for(guild.me).read_message_history or not channel.permissions_for(guild.me).view_channel:
                            with self.store.db:self.queue.gap(channel.id,'0','channel-permission')
                            continue
                        if self.store.db.execute('SELECT COUNT(*) FROM discord_queue').fetchone()[0]>2000:break
                        row=self.store.db.execute('SELECT * FROM discord_coverage WHERE channel=?',(str(channel.id),)).fetchone()
                        since=row['since'] if row else (datetime.now(timezone.utc)-timedelta(days=30) if self.config.get('initialHistoryEnabled',False) else datetime.fromtimestamp(self.started,timezone.utc)).isoformat()
                        after=discord.Object(id=int(row['cursor'])) if row and row['cursor'] else datetime.fromisoformat(since)
                        try:
                            found=[]
                            async for m in channel.history(limit=100,after=after,oldest_first=True):found.append(m.id)
                            with self.store.db:
                                for mid in found:self.queue.enqueue(guild.id,channel.id,mid)
                                self.store.db.execute('INSERT OR REPLACE INTO discord_coverage VALUES(?,?,?,?,?,?)',
                                    (str(channel.id),str(guild.id),str(found[-1]) if found else (row['cursor'] if row else None),since,
                                     'pending-history' if len(found)==100 else 'caught-up-ids',now()))
                            # Repairs recent edits after missed events; no inference of deletion from absence.
                            async for m in channel.history(limit=20,after=datetime.fromisoformat(since)):
                                self.add(guild.id,channel.id,m.id)
                        except discord.HTTPException:
                            with self.store.db:self.queue.gap(channel.id,'0','history-access')
                self.status()
            except Exception:
                self.metrics['errors']+=1;self.status()
            try:await asyncio.wait_for(self.reconcile_now.wait(),timeout=900)
            except asyncio.TimeoutError:pass

    async def close(self):
        if self._storage_closed:return
        for task in self.tasks:task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        self.connected=False;self.status()
        await super().close()
        self._storage_closed=True
        self.store.db.close()


def main():
    import fcntl
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,default=Path.home()/'Library/Application Support/ChatScheduleHub/discord-bot.json')
    parser.add_argument('--seconds',type=int,default=0)
    args=parser.parse_args();config=json.loads(args.config.read_text());root=args.config.parent
    require(config.get('liveCollectionEnabled') is True and config.get('externalProcessingAllowed') is True,'live collection must be enabled')
    lock=open(root/'discord-worker.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    api=DiscordBot(config);api.verify()
    async def run():
        async with Collector(config,root) as client:
            if args.seconds:
                try:await asyncio.wait_for(client.start(api._token),args.seconds)
                except asyncio.TimeoutError:pass
            else:await client.start(api._token)
    asyncio.run(run())


if __name__=='__main__':main()
