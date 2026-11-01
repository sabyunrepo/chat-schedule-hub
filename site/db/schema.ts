import { sqliteTable, text, integer, primaryKey } from 'drizzle-orm/sqlite-core';
export const preferences = sqliteTable('preferences', { userId:text('user_id').notNull(), tab:text('tab').notNull(), value:text('value').notNull(), version:integer('version').notNull(), updated:text('updated').notNull() }, t=>[primaryKey({columns:[t.userId,t.tab]})]);
export const snapshots=sqliteTable('snapshots',{owner:text('owner').primaryKey(),installation:text('installation').notNull(),sequence:integer('sequence').notNull(),payload:text('payload').notNull(),updated:text('updated').notNull()});
export const pairings=sqliteTable('pairings',{hash:text('hash').primaryKey(),owner:text('owner').notNull(),created:text('created').notNull()});
