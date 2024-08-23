const path = require('path');
const webpack = require('webpack');

module.exports = {
  entry: './src/index.js',  // adjust this to your entry point
  output: {
    filename: 'bundle.js',
    path: path.resolve(__dirname, 'dvmdash/monitor/static/js'),
  },
  module: {
    rules: [
      {
        test: /\.(js|jsx)$/,
        exclude: /node_modules/,
        use: {
          loader: 'babel-loader',
          options: {
            presets: ['@babel/preset-env', '@babel/preset-react']
          }
        }
      },
      {
        test: /\.css$/,
        use: ['style-loader', 'css-loader']
      }
    ]
  },
  resolve: {
    extensions: ['.js', '.jsx']
  },
  plugins: [
    new webpack.ProvidePlugin({
      React: 'react',
      ReactDOM: 'react-dom'
    })
  ]
};