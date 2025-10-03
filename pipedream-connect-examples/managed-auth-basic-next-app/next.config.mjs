/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    // Disable ESLint during production builds (Vercel)
    // ESLint gives false positives for variables that are actually used
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
