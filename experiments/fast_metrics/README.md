# Computing fast metrics

The current system keeps getting these errors from MongoDB:

```
"Query Targeting: Scanned Objects / Returned has gone above 1000
 
The ratio of documents scanned to returned exceeded 1000.0 on  cluster0-shard-xxxxxxx.mongodb.net, which typically suggests that un-indexed queries are being run. "
```

This is because we are running an aggregation pipeline over all documents in the collection, and it's constantly growing. 

The first experiment we're going to try is to compare the aggregation pipeline vs batch processing that iterateively updates metrics as new data comes in.

