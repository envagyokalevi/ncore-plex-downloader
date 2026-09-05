/** Magyar nyelvű formázó segédfüggvények. */

export function formatSize(bytes: number | null | undefined, fallback = '?'): string {
  if (bytes === null || bytes === undefined || bytes < 0) return fallback
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  const decimals = unit === 0 ? 0 : value >= 100 ? 0 : value >= 10 ? 1 : 2
  return `${value.toFixed(decimals).replace('.', ',')} ${units[unit]}`
}

export function formatSpeed(bytesPerSecond: number | null | undefined): string {
  if (!bytesPerSecond) return '0 B/s'
  return `${formatSize(bytesPerSecond)}/s`
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '–'
  if (seconds < 60) return `${seconds} mp`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} perc`
  const hours = Math.floor(minutes / 60)
  const restMinutes = minutes % 60
  if (hours < 24) return restMinutes ? `${hours} ó ${restMinutes} p` : `${hours} óra`
  const days = Math.floor(hours / 24)
  return `${days} nap ${hours % 24} ó`
}

export function formatPercent(progress: number): string {
  return `${(progress * 100).toFixed(progress >= 1 ? 0 : 1).replace('.', ',')}%`
}
