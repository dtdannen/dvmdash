# How we calculate metrics


## Event Count Metrics

**DVM Requests**: This is the number of events between kind 5000-5999 of all time

**DVM Results**: This is the number of events between kind 6000-6999 of all time

**DVM Request Kinds**: Size of the set of all kinds seen where the kind number is between 5000-5999

**DVM Result Kinds**: Size of the set of all kinds seen where the kind number is between 6000-6999

**DVM Pub Keys Seen**: We take all events that a DVM might produce (kinds 6000-6999, 7000, and 31990) count
the number of unique DVM pub keys among them. For Kinds 7000 we check that there is a payment-required tag. For Kind 31990 events, we check that the "k"
 tag has a value between "5000"-"5999".

**DVM Profiles Seen**: Number of all 31990 events that have a "k" tag value between 5000 and 5999







