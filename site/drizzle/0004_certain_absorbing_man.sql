CREATE TABLE `chat_threads` (
	`owner` text NOT NULL,
	`id` text NOT NULL,
	`title` text NOT NULL,
	`updated` text NOT NULL,
	`lease` text NOT NULL,
	`until` integer NOT NULL,
	PRIMARY KEY(`owner`, `id`)
);
--> statement-breakpoint
CREATE TABLE `chat_turns` (
	`owner` text NOT NULL,
	`thread` text NOT NULL,
	`id` text NOT NULL,
	`question` text NOT NULL,
	`reply` text,
	`status` text NOT NULL,
	`created` text NOT NULL,
	PRIMARY KEY(`owner`, `thread`, `id`)
);
