document.addEventListener('DOMContentLoaded', () => {
  // Auto-dismiss flash alerts after 4s
  document.querySelectorAll('.alert.alert-dismissible').forEach(el => {
    setTimeout(() => bootstrap.Alert.getOrCreateInstance(el)?.close(), 4000);
  });

  // Active nav link highlight
  const path = window.location.pathname;
  document.querySelectorAll('.bms-navbar .nav-link').forEach(link => {
    try {
      const href = new URL(link.href).pathname;
      if (href !== '/' && path.startsWith(href)) link.classList.add('active');
      if (href === '/' && path === '/') link.classList.add('active');
    } catch(_) {}
  });
});
