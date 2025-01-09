# Database and Batch Processor Performance Test Report

## Overview
Today I conducted the first comprehensive performance test of our database and batch processor system, specifically focusing on metric calculations. The test processed just over 2 million DVM events from the past 18 months, serving as an initial benchmark for our system's scalability capabilities.

## Test Objectives
The primary goal was to evaluate the system's performance characteristics, with a target of processing millions of events per hour at a cost-effective rate. This test represents the first step in ensuring our infrastructure can handle increasing DVM event volumes efficiently.

## Results

![redis_queue_size_with_rate_20250108_005437.png](..%2Fexperiments%2Fgraphs%2Fredis_queue_size_with_rate_20250108_005437.png)

### Performance Metrics
- Initial processing rate: ~40,000 events per minute
- Final processing rate: ~10,000 events per minute
- Test environment: $25 Digital Ocean instance
- Test data location: `experiments/data/yellow-goat_2025-01-07_12-41PM_metrics.csv`

### Key Findings
The test revealed significant performance degradation over time, with processing speeds dropping by approximately 75% from start to finish. While initial analysis suggests full table scans might be contributing to this decline, particularly on the entity activity table, further investigation is needed to confirm the root cause of the performance degradation.

### Performance Bottlenecks
1. Database Schema Limitations
   - Current schema design requires full table scans, leading to decreased performance as data volume grows
   - No efficient mechanism for historical data cleanup
   - Scaling issues with increasing data volume

2. Resource Utilization
   - Processing speed degradation indicates inefficient query patterns
   - Current architecture may not support optimal horizontal scaling

## Impact Analysis
The current implementation falls short of our scalability requirements. As DVM activity increases across the network, computational costs would grow disproportionately under the present architecture. This directly conflicts with our goal of maintaining cost-efficient scaling, where we aim for only a 10-20% cost increase for every 10x increase in event rate.

## Recommendations
1. Database Schema Redesign
   - Optimize schema to eliminate full table scans
   - Implement efficient indexing strategies
   - Design for data retention and cleanup capabilities

2. Batch Processor Optimization
   - Refactor for horizontal scaling capabilities
   - Implement efficient query patterns
   - Consider partitioning strategies for improved performance

## Next Steps
The immediate priority is to revisit both the database schema and batch processor design. Focus areas include:
1. Investigating root causes of performance degradation
2. Implementing and testing data cleanup mechanisms
3. Optimizing query patterns
4. Designing for horizontal scalability
5. Establishing clear data retention policies

## Future Test Requirements
The next performance test should include:
1. Time-ordered event ingestion to simulate real-world patterns
2. Implementation and verification of cleanup mechanisms
3. Continuous monitoring and plotting of database memory usage
4. Investigation of performance degradation causes through detailed metrics

These additions will help identify memory constraints and verify the effectiveness of cleanup mechanisms in maintaining stable performance.

## Conclusion
This performance test has provided valuable insights into our system's current limitations. While the results didn't meet our desired performance targets, identifying these issues early allows us to address fundamental architectural challenges before adding more features or scaling the system further.