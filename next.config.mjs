/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: { domains: [] },
  webpack: (config) => {
    config.module.rules.push({ test: /\.geojson$/, type: 'json' })
    // CesiumJS ships large pre-built ESM with dynamic requires; silence the false-positive context warnings.
    config.module.unknownContextCritical = false
    config.module.exprContextCritical = false
    return config
  },
}

export default nextConfig
