CREATE INDEX `chat_threads_owner_updated` ON `chat_threads` (`owner`,`updated`);--> statement-breakpoint
CREATE INDEX `chat_turns_owner_thread_created` ON `chat_turns` (`owner`,`thread`,`created`);--> statement-breakpoint
CREATE INDEX `chat_turns_owner_created` ON `chat_turns` (`owner`,`created`);--> statement-breakpoint
CREATE INDEX `sync_records_owner_kind_id_updated` ON `sync_records` (`owner`,`kind`,`id`,`updated`);