# Deviations from the pre-registration

Changes made after the tag `prereg-2026-10-17` (commit 03fc011), each written and committed before the work it changes. The results report every one.

## 1. Latency windows (17 October 2026, about 17:30 London, before any latency call)

Pre-registered: two latency windows, London morning and US afternoon, 300 items each.

Run instead: both windows on the evening of Saturday 17 October, one straight after the other, so the whole benchmark finishes in one evening. Window 1 ("evening-a") starts as soon as the accuracy, Opus medium and stability runs finish, at about 17:45 London (12:45 US Eastern); window 2 ("evening-b") starts as soon as window 1 ends, about ten minutes later. Everything else about latency is unchanged: 300 items per window plus 20 warm-up calls, one request at a time, each item sent to the systems in a random order, Opus only on its sample items.

What this costs: the two windows are minutes apart at one time of day, in the US working day, so they act as one sample of 600 items and the results cannot say whether speed changes with time of day or US traffic. The write-up says so next to the latency figures.

(An earlier version of this entry, committed a few minutes before, kept window 2 at 21:00 London. Changed before any latency call.)

Decided by Gbolagade Ishola.
