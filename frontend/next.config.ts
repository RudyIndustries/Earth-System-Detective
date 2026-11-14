import type { NextConfig } from 'next';

const config: NextConfig = {
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:3001';
    return [{ source: '/api/:path*', destination: `${backend.replace(/\/$/, '')}/api/:path*` }];
  },
};

export default config;
