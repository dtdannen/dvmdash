# Diving Deep into DVM Development: An Update on the dvmdash Project

## Introduction

Hello Nostr community! I'm excited to provide an update on the dvmdash project. While I had hoped to announce the website launch by now, I want to share our progress and the exciting developments we've made. 

## Progress Highlights

### Shifting Gears for Better Understanding

Initially, our plan was to build the metrics portion of the webapp by the end of June 2024, launch it, and then start on the graph-based debugging tools. However, while developing the metrics calculations, I realized the importance of fully understanding the event flow between DVMs and users. This led to a strategic decision:

- We've prioritized building the graph-based debugging tool ahead of schedule.
- While this means a slight delay in achieving milestones M1 and M2, we're now close to hitting milestones M3 and M4 significantly ahead of time.

### Overcoming Unexpected Challenges

Our journey hasn't been without its hurdles. We've faced and overcome two major unexpected challenges:

1. **Cache Service Complexity**: Setting up a cache service to continuously collect all DVM-related events proved more challenging than anticipated, involving a range of unforeseen issues.

2. **Graph Visualization Struggles**: Finding and integrating a suitable graph visualization library was surprisingly difficult. After trying at least three different libraries, we finally settled on a JavaScript version of graphviz.

### New Feature Alert: Frontend Playground

While testing the graph visualization library, we built a simple frontend playground page. This unexpected addition allows users to:

- Send live DVM requests
- View all related events created from DVMs in real-time

Though not initially scoped, this frontend client for DVM use has garnered interest from multiple developers and has proven incredibly useful in our own testing processes.

## User Feedback

As we develop this tool to assist devs working with DVMs, we've been actively seeking and receiving valuable feedback:

- **Fanfares.io Developers**: During a demo, they described dvmdash as feeling foundational for DVM activity on Nostr, comparing its potential role to that of mempool.space for the Bitcoin network.

- **New DVM Developers**: Discussions with a friend starting to build his own DVMs highlighted the frustration caused by the lack of a playground tool, which motivated the creation of our new frontend playground.

- **Alby Team**: We've been invited to demo the app to the Alby developers, a demonstration we're looking forward to scheduling soon.

## Next Steps: The Road to Launch

Before we launch, we're focusing on completing the following key features:

1. **Global Payment Metrics**: Adding metrics about payments to answer the question: "How much have DVMs been paid?"

2. **Enhanced Graph Database**: Configuring Neo4j to store payment invoices, receipts, and connections to other events, enabling the graph-based debugger to display these as nodes.

3. **DVM Browser Page**: Fleshing out with DVM-specific metrics, including:
   - Number of requests and responses
   - DVM's first online timestamp

4. **Kind Browser Page**: Improving with:
   - Kind descriptions
   - Request and response statistics
   - Recent request listings

5. **Real-time Event Processing**: Setting up the pipeline for new events to be processed into nodes in the semantic graph as they occur.

6. **Documentation**: Updating the README with local setup instructions, including database requirements (MongoDB and Neo4j).

## Join Us for a Live Demo!

We're planning a zap.stream event where I'll provide an overview of the app and demonstrate how to use it. This session will be recorded for those who can't attend live, ensuring everyone can benefit from the walkthrough.

## Closing Thoughts

Once again, I want to express my deepest gratitude for the grant that's making this work possible. The dvmdash project is shaping up to be a fundamental tool for the Nostr ecosystem, and I'm thrilled about its potential impact on DVM development and usage.

Stay tuned for more updates, and thank you for your continued support and interest in dvmdash!

Sincerely,
Dustin Dannenhauer