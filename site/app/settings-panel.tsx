'use client';
import {Bell,Link2,Download,ChevronRight} from 'lucide-react';
import {Reminders} from './reminders';
export function SettingsPanel({signed,onConnect,install}:{signed:boolean;onConnect:()=>void;install?:()=>void}){
 return <div className="settings-page"><section className="settings-section"><h2>일정 채팅</h2><p className="setting-description">Codyssey · GPT-5.4 mini</p><p className="setting-description">질문·최근 대화·조회한 일정과 근거 일부를 Codyssey API로 전송합니다. 대화 기록은 내 계정에 저장됩니다.</p></section><section className="settings-section"><h2><Bell size={17}/>알림</h2>{signed?<Reminders/>:<p className="setting-description">로그인 후 알림을 설정할 수 있습니다.</p>}</section><section className="settings-section"><h2><Link2 size={17}/>수집 연결</h2><button className="settings-link" onClick={onConnect}><span><strong>연결된 소스</strong><small>카카오톡 · Discord · 메일 · Google Calendar</small></span><ChevronRight size={18}/></button></section>{install&&<section className="settings-section"><h2><Download size={17}/>앱</h2><button className="settings-link" onClick={install}><span>모아 설치</span><ChevronRight size={18}/></button></section>}</div>
}
