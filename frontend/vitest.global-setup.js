// Vitest gives each test worker a fixed 60 s, which cannot be configured, to
// start, and that includes loading the jsdom environment. Where first-time file
// reads are slow (for example antivirus scanning node_modules on Windows), a
// cold jsdom load can exceed it and the run fails before any test executes.
// Loading jsdom once here, before any worker starts, leaves its files cached so
// the workers start well within the limit.
export default async function warmJsdom() {
  await import('jsdom')
}
