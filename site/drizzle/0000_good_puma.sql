CREATE TABLE `pairings` (
	`hash` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`created` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `preferences` (
	`user_id` text NOT NULL,
	`tab` text NOT NULL,
	`value` text NOT NULL,
	`version` integer NOT NULL,
	`updated` text NOT NULL,
	PRIMARY KEY(`user_id`, `tab`)
);
--> statement-breakpoint
CREATE TABLE `snapshots` (
	`owner` text PRIMARY KEY NOT NULL,
	`installation` text NOT NULL,
	`sequence` integer NOT NULL,
	`payload` text NOT NULL,
	`updated` text NOT NULL
);
