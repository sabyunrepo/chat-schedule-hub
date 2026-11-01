CREATE TABLE `push_deliveries` (
	`owner` text NOT NULL,
	`subscription` text NOT NULL,
	`item` text NOT NULL,
	`state` text NOT NULL,
	`lease` text NOT NULL,
	`until` integer NOT NULL,
	`attempts` integer NOT NULL,
	PRIMARY KEY(`owner`, `subscription`, `item`)
);
--> statement-breakpoint
CREATE TABLE `push_settings` (
	`owner` text PRIMARY KEY NOT NULL,
	`public_key` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `push_subscriptions` (
	`owner` text NOT NULL,
	`id` text NOT NULL,
	`payload` text NOT NULL,
	`created` text NOT NULL,
	PRIMARY KEY(`owner`, `id`)
);
