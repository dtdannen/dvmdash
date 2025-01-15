# DVMDash Data Retention and Schema FAQ

## Contents
1. [Core Concepts](#core-concepts)
   - What is the data retention strategy?
   - What data is kept and for how long?
   - How do we handle historical data?

2. [Table Structure](#table-structure)
   - Purpose of each table
   - How tables relate to each other
   - Data flow through the system

3. [Data Management](#data-management)
   - Growth control for each table
   - Cleanup processes
   - Entity lifecycle management

4. [Common Usage](#common-usage)
   - Querying recent vs historical data
   - Working with active/inactive entities
   - Example queries and use cases

5. [Technical Implementation](#technical-implementation)
   - Cleanup process details
   - Monitoring and maintenance
   - Troubleshooting

## Core Concepts

### Q: What's the high-level overview of the data retention strategy?
A: DVMDash uses a tiered data retention strategy:
- **Rolling 30-Day Window**: Maintain detailed metrics and activity data for the most recent 30 days
- **Monthly Historical**: Aggregate completed months into monthly summaries
- **Entity Lifecycle**: Track active/inactive status for DVMs and users using a rolling window
- **Daily Cleanup**: Continuous cleanup to maintain a precise 30-day window

The rolling window approach means:
- At any point, users see exactly 30 days of detailed data
- Data older than 30 days is continuously cleaned up
- Monthly aggregates are created independently of the rolling window
- No gaps in data visibility at month boundaries

### Q: What data do we keep beyond the 30-day window?
A: We maintain two types of historical data:

1. **Running Totals in Global Stats**
   - Cumulative metrics like total requests, responses
   - Running counts of unique entities seen
   - These provide all-time aggregate numbers
   - Updated with each new event
   - No granular historical data, just current totals

2. **Monthly Activity Records**
   - Detailed monthly snapshots
   - Includes metrics like:
     * Total requests/responses per month
     * Unique DVMs/users/kinds per month
     * Most popular DVM and kind for that month
   - Allows historical trend analysis
   - Preserves monthly granularity

### Q: Why 30 days? Why not keep everything?
A: The 30-day window was chosen for several reasons:
- Cost-effective storage usage
- Maintains high query performance for recent data
- Covers the most commonly needed timeframe for analysis
- Provides sufficient data for trend analysis while keeping storage bounded

## Table Structure

### Q: What is each table's purpose?

#### Real-time Processing Tables
- `entity_activity`: Tracks all entity interactions within the 30-day window
- `time_window_stats`: Pre-computed metrics for different time intervals (1hr, 24hr, 7d)
- `global_stats_rollups`: System-wide statistics with running totals
- `dvm_stats_rollups`: DVM-specific performance metrics
- `kind_stats_rollups`: Statistics per kind of DVM job

#### Entity Tables
- `dvms`: Core DVM information with activity status
- `users`: User information with activity status
- `kind_dvm_support`: Tracks which DVMs support which kinds

#### Historical Tables
- `monthly_activity`: Long-term storage of monthly aggregated metrics
- `cleanup_log`: Historical record of deactivated entities


## Data Management

### Q: How is unbounded growth prevented for each table?
A: Each table has specific growth control mechanisms:

1. **Entity Tables**
   - `dvms` and `users`: Two-phase cleanup process
     * Phase 1: Mark inactive after 30 days of no activity
     * Phase 2: Delete after another 30 days of no activity (60 days total)
     * If entity becomes active again, it's reactivated
     * Maximum lifespan of any record is 60 days unless there's new activity

2. **Activity and Stats Tables**
   - `entity_activity`: Bounded by 35-day retention window
   - `time_window_stats`: Bounded by 35-day retention window
   - `dvm_stats_rollups`: Bounded by 35-day retention window
   - `kind_stats_rollups`: Bounded by 35-day retention window
   - `kind_dvm_support`: Automatically cleaned up when DVMs are deleted

3. **Historical Tables**
   - `cleanup_log`: Controlled by either:
     * Time-based deletion (e.g., delete records older than 1 year)
     * Space-based constraints (e.g., keep table under X GB)
   - `monthly_activity`: Grows very slowly (1 row per month)
     * Consider archiving or aggregating data older than X years if needed

### Q: How often do cleanup processes run?
A: The system maintains a precise rolling window through multiple processes:

1. Daily Rolling Window Cleanup:
   - Remove data older than 30 days from entity_activity
   - Update activity status for DVMs and users
   - Maintain rolling window for all activity-based tables
   - Example: On January 15th, we keep data from December 16th through January 15th

2. Two-Phase Entity Cleanup (runs daily):
   - Phase 1: Mark entities inactive if no activity in last 30 days
   - Phase 2: Delete entities if inactive for another 30 days (60 days total)
   - This runs on a rolling basis, not tied to calendar months

3. Monthly Aggregation (runs on 1st of month):
   - Calculate statistics for the completed month
   - Store in monthly_activity table
   - Independent of rolling window cleanup
   - Example: On February 1st, aggregate all January data

4. Maintenance Cleanup (as needed):
   - cleanup_log maintenance based on size/time thresholds
   - Archive or delete old monthly aggregates if needed

## Common Usage

### Q: How do I calculate all-time totals?
A: All-time totals are calculated by combining historical monthly data with current rolling window data:


### Q: How do I get accurate unique counts for the last 30 days?
A: Use the `entity_activity` table with a 30-day window:

### Q: How do I get historical trends beyond 30 days?
A: Use the `monthly_activity` table:


### Q: What happens if a DVM returns after being marked inactive?
A: The system will:
1. Detect new activity in `entity_activity`
2. Update the `last_seen` timestamp
3. Set `is_active = TRUE` in the `dvms` table
4. Begin tracking metrics in rollup tables again

## Technical Implementation

### Q: How should cleanup processes be implemented technically?
A: Best practices for implementing the cleanup processes:

1. Use transactions to maintain consistency
2. Implement cleanup in batches to avoid long-running transactions
3. Consider table locks and database performance
4. Log all cleanup activities for auditing
5. Include error handling and retry mechanisms


### Q: What monitoring should I add?
Monitor these key metrics:
1. Size of `entity_activity` table (should be bounded by 30 days of data)
2. Ratio of active to inactive entities in `dvms` and `users` tables
3. Growth rate of `monthly_activity` table
4. Execution time of the monthly cleanup process

### Q: What about backup and recovery?
Best practices for this schema:
1. Regular backups of all tables
2. Special attention to `monthly_activity` as it contains irreplaceable historical data
3. Keep multiple backup points for the cleanup process
4. Consider point-in-time recovery for the 30-day window

### Q: How do we deal with old events?
We perform monthly backups after we get an event with a timestamp for a new month. 
- The event collector prevents getting events too far in the future (more than 15 minutes).
- Events older than the current month are ignored. Otherwise, all events will be collected and processed as long as they are within the current month. 
- Once we transition to a new month, we ignore any events from prior months. 
- This does assume we receive at least one DVM event a month
- When we are backtesting, we will set the current month and year based on events as we get them. In production, we will use the current date for setting the current month and year.
- Because there could be a lag

- EVENTS IN THE REDIS QUEUE ARE THE GROUND TRUTH
- To make sure we dont screw up the time window stats, we need finer grained windows in the analyze events, so the period start and end can't cross a day boundary. if it does, put it into the overflow. We process the earliest day. We can track each day's events with a dictionary, anything but the earliest day is put into overflow. If the event is from an earlier month, they can eat crap aka it gets ignored, becuase we will aghve a bigger buffer.
- it doesn't matter if the buffer is big and we store like 3 days of events for the next month, because the monthly cleanup will take care of all of that, we will do the cleanup for th emonth before and those events will be ignored.
- also the backtest data processing and moving to next month will be the same in and out of production. we can't use current date and time because if there's back pressure, we could be days behind in processing events if there's a huge influx and we haven't scaled up yet. SO THEREFORE the redis queu is the ground truth for current date and time. Also it makes backtesing easier. 


### Situations
- events in batch are in the next month and we haven't done a monthly update yet
  - analyze them anyway

- left off wrapping up the new monthly cleanup logic and double checking that analyze events will properly trigger monthly cleanup - i believe that currently monthly cleanup will just need to happen if the boolean flag we made is set (i.e. we ever saw a future month timestamp past the buffer)

- BUT WHAT IF YOU GET A FULL BATCH that is before the buffer deadline? Are you going to process it just fine?  NO YOU WONT BECAUSE WE HAVE A DEADLOCK RIGHT NOW WHEN WE"RE WAITING IN BETWEEN THE BUFFER AND BECUASE WE WANT TO AVOID A MONTHLY OVERLAP IN BATCHES
- 