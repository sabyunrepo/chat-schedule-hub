CREATE TABLE `event_history` (
	`owner` text NOT NULL,
	`id` text NOT NULL,
	`revision` text NOT NULL,
	`payload` text NOT NULL,
	`created` text NOT NULL,
	PRIMARY KEY(`owner`, `id`, `revision`)
);
--> statement-breakpoint
CREATE TABLE `review_actions` (
	`owner` text NOT NULL,
	`id` text NOT NULL,
	`revision` text NOT NULL,
	`state` text NOT NULL,
	`comment` text NOT NULL,
	`version` integer NOT NULL,
	`updated` text NOT NULL,
	PRIMARY KEY(`owner`, `id`)
);
--> statement-breakpoint
CREATE TABLE `review_history` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`item` text NOT NULL,
	`payload` text NOT NULL,
	`created` text NOT NULL
);
