const http = require('http');
const fs = require('fs');
const path = require('path');

const server = http.createServer((req, res) => {
    const filePath = path.join(__dirname, 'test-api.html');
    fs.readFile(filePath, (err, content) => {
        if (err) {
            res.writeHead(500);
            res.end('Error loading test page');
            return;
        }
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(content);
    });
});

server.listen(3001, () => {
    console.log('Test server running at http://localhost:3001');
});
