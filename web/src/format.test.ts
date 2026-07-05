import { describe, it, expect } from 'vitest'
import { fmtB, fmtDur, fmtUp } from './main'

describe('fmtB', () => {
  it('returns 0 B for zero', () => {
    expect(fmtB(0)).toBe('0 B')
  })

  it('formats bytes', () => {
    expect(fmtB(500)).toBe('500.0 B')
  })

  it('formats kilobytes', () => {
    expect(fmtB(1024)).toBe('1.0 KB')
    expect(fmtB(1536)).toBe('1.5 KB')
  })

  it('formats megabytes', () => {
    expect(fmtB(1048576)).toBe('1.0 MB')
  })

  it('formats gigabytes', () => {
    expect(fmtB(1073741824)).toBe('1.0 GB')
  })
})

describe('fmtDur', () => {
  it('formats seconds only', () => {
    expect(fmtDur(30)).toBe('30s')
    expect(fmtDur(59)).toBe('59s')
  })

  it('formats minutes and seconds', () => {
    expect(fmtDur(60)).toBe('1m 0s')
    expect(fmtDur(90)).toBe('1m 30s')
    expect(fmtDur(3661)).toBe('61m 1s')
  })
})

describe('fmtUp', () => {
  it('formats zero as 0m', () => {
    expect(fmtUp(0)).toBe('0m')
  })

  it('formats minutes only', () => {
    expect(fmtUp(300)).toBe('5m')
  })

  it('formats hours and minutes', () => {
    expect(fmtUp(3600)).toBe('1h 0m')
    expect(fmtUp(5400)).toBe('1h 30m')
  })

  it('formats days, hours, and minutes', () => {
    expect(fmtUp(86400)).toBe('1d 0m')
    expect(fmtUp(90000)).toBe('1d 1h 0m')
  })
})
