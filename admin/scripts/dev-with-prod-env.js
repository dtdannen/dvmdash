// Load production environment variables but run in development mode
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

// Path to .env.production
const envPath = path.join(__dirname, '..', '.env.production');

// Read the .env.production file
try {
  const envFile = fs.readFileSync(envPath, 'utf8');
  
  // Parse the environment variables
  const envVars = {};
  envFile.split('\n').forEach(line => {
    // Skip comments and empty lines
    if (line.trim() === '' || line.startsWith('#')) return;
    
    const [key, ...valueParts] = line.split('=');
    const value = valueParts.join('='); // Rejoin in case value contains = characters
    
    if (key && value) {
      envVars[key.trim()] = value.trim();
    }
  });
  
  console.log('Loaded environment variables from .env.production:');
  console.log(Object.keys(envVars).join(', '));
  
  // Start Next.js dev server with the production environment variables
  const nextDev = spawn('npx', ['next', 'dev'], {
    env: { ...process.env, ...envVars },
    stdio: 'inherit'
  });
  
  nextDev.on('close', (code) => {
    process.exit(code);
  });
  
} catch (error) {
  console.error('Error loading .env.production file:', error);
  process.exit(1);
}
