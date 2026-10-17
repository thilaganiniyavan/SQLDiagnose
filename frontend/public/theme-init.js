// Applies the saved theme before the first paint (kept external for the Content-Security-Policy).
;(function () {
  var theme = 'system'
  try { theme = localStorage.getItem('sqld.theme') || 'system' } catch (e) {}
  var dark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
})()
