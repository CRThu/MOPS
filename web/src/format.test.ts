import { describe, it, expect } from 'vitest'
import { fmtBytes, fmtDuration, fmtUptime } from './format'

describe('fmtBytes', () => {
  it('returns 0 B for zero', () => {
    expect(fmtBytes(0)).toBe('0 B')
  })

  it('formats bytes', () => {
    expect(fmtBytes(500)).toBe('500.0 B')
  })

  it('formats kilobytes', () => {
    expect(fmtBytes(1024)).toBe('1.0 KB')
    expect(fmtBytes(1536)).toBe('1.5 KB')
  })

  it('formats megabytes', () => {
    expect(fmtBytes(1048576)).toBe('1.0 MB')
  })

  it('formats gigabytes', () => {
    expect(fmtBytes(1073741824)).toBe('1.0 GB')
  })
})

describe('fmtDuration', () => {
  it('formats seconds only', () => {
    expect(fmtDuration(30)).toBe('30s')
    expect(fmtDuration(59)).toBe('59s')
  })

  it('formats minutes and seconds', () => {
    expect(fmtDuration(60)).toBe('1m 0s')
    expect(fmtDuration(90)).toBe('1m 30s')
    expect(fmtDuration(3661)).toBe('61m 1s')
  })
})

describe('fmtUptime', () => {
  it('formats zero as 0m', () => {
    expect(fmtUptime(0)).toBe('0m')
  })

  it('formats minutes only', () => {
    expect(fmtUptime(300)).toBe('5m')
  })

  it('formats hours and minutes', () => {
    expect(fmtUptime(3600)).toBe('1h 0m')
    expect(fmtUptime(5400)).toBe('1h 30m')
  })

  it('formats days, hours, and minutes', () => {
    expect(fmtUptime(86400)).toBe('1d 0m')
    expect(fmtUptime(90000)).toBe('1d 1h 0m')
  })
})
