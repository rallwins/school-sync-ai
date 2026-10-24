# ADR 0003: Duplicate detection and ownership of synced events

Status: accepted.

**Decision.** Two identities:
- `fingerprint`: hash of current visible content (title, dates, duration, times, timezone),
  recomputed server-side because users edit events after extraction.
- `stable_id`: school + academic year + start date. It deliberately excludes the PDF hash so a
  revised PDF maps onto the same event slots.

Three layers when planning a sync (`deduplication/reconcile.py`):
A. **Ours**: stable id found in the manifest or as a provider event carrying our private
   extended property -> skip if the fingerprint matches, otherwise update.
B. **Identical but not ours**: skip and leave untouched.
C. **Look-alike**: similar title (character ratio or fuzzy token containment) on overlapping dates
   but different time/duration -> `conflict`, for a person to decide.

The app only updates or deletes provider events that carry its owner property; adapters enforce this
independently of the planner (`NotOwned`). Removals are proposed, never executed. A mapping row
whose provider event vanished is a conflict, not a silent recreate. Retries reconcile first: before
(re)creating, the provider is queried for our owner id, which handles the "request succeeded,
response lost" case.

**Known limits.** A date change in a revised PDF appears as one removal plus one addition. ICS file
import cannot be protected against duplicates inside third-party clients. Fuzzy matching only feeds
the conflict path, so false positives cost a click, not a wrong write.
