// infrastructure/mongodb/init.js

// Switch to admin database first
db = db.getSiblingDB('admin');

// Create application user
db.createUser({
  user: 'devuser',
  pwd: 'devpass',
  roles: [
    { role: 'readWrite', db: 'dvmdash' }
  ]
});

// Switch to application database
db = db.getSiblingDB('dvmdash');

// Create collections and indexes
db.createCollection('events');

db.events.createIndex({ "event_id": 1 }, { unique: true });
db.events.createIndex({ "kind": 1 });
db.events.createIndex({ "created_at": 1 });
db.events.createIndex({ "dvm_id": 1 });