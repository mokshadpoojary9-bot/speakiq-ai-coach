import { describe, expect, it } from 'vitest'
import { countWords, formatBytes, formatInterval, formatPercent, formatTime } from './format'

describe('format helpers', () => {
  it('formats seconds as m:ss.s', () => {
    expect(formatTime(0)).toBe('0:00.0')
    expect(formatTime(7.5)).toBe('0:07.5')
    expect(formatTime(75.5)).toBe('1:15.5')
    expect(formatTime(-3)).toBe('0:00.0')
  })

  it('formats intervals, percentages and sizes', () => {
    expect(formatInterval({ start: 4, end: 7.5 })).toBe('0:04.0 – 0:07.5')
    expect(formatPercent(0.486)).toBe('49%')
    expect(formatBytes(512 * 1024)).toBe('512 KB')
    expect(formatBytes(25 * 1024 * 1024)).toBe('25.0 MB')
  })

  it('counts words, ignoring extra whitespace', () => {
    expect(countWords('')).toBe(0)
    expect(countWords('   ')).toBe(0)
    expect(countWords('  good   morning\neveryone ')).toBe(3)
  })
})
