/**
 * MOPS Dashboard — formatting helpers
 */

export const fmtBytes = (b: number): string => {
  if (!b || b === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(b) / Math.log(1024))
  return (b / 1024 ** i).toFixed(1) + ' ' + units[i]
}

export const fmtSpeed = (bytesPerSec: number): string => {
  if (!bytesPerSec || bytesPerSec === 0) return '0 B/s'
  return fmtBytes(bytesPerSec) + '/s'
}

export const fmtDuration = (sec: number): string => {
  if (sec < 60) return `${Math.floor(sec)}s`
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}m ${s}s`
}

export const fmtUptime = (sec: number): string => {
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return (d ? d + 'd ' : '') + (h ? h + 'h ' : '') + m + 'm'
}

export const fmtNodeLabel = (hostname: string, ip: string, port: number): string => {
  return `${hostname}\n${ip}:${port}`
}
