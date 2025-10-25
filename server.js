require('dotenv').config();
const app = require('./src/app');
const connectDB = require('./src/config/database');
const fs = require('fs');
const path = require('path');

// Connect to database
connectDB();

// Create necessary directories if they don't exist
const uploadsDir = path.join(__dirname, 'public/uploads');
const profilesDir = path.join(uploadsDir, 'profiles');
const tracksDir = path.join(uploadsDir, 'tracks');

if (!fs.existsSync(uploadsDir)) {
  fs.mkdirSync(uploadsDir, { recursive: true });
}

if (!fs.existsSync(profilesDir)) {
  fs.mkdirSync(profilesDir);
}

if (!fs.existsSync(tracksDir)) {
  fs.mkdirSync(tracksDir);
}

// Define port
const PORT = process.env.PORT || 5001;

// Start server
const server = app.listen(
  PORT,
  console.log(`Server started in ${process.env.NODE_ENV} mode on port ${PORT}`)
);

// Handle unhandled promise rejections
process.on('unhandledRejection', (err) => {
  console.log('Unhandled error:', err.message);
  // Close server & exit process
  server.close(() => process.exit(1));
});