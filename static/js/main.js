/* StarEastStore storefront behaviour.
   Note: all security-sensitive logic (pricing, stock, totals) lives on the
   server; this file only improves UX. */
(function () {
  'use strict';

  // Cart badge helper: update count everywhere when a form submits.
  function updateCartBadge(delta) {
    document.querySelectorAll('[data-cart-count]').forEach(function (badge) {
      var current = parseInt(badge.textContent || '0', 10) + delta;
      badge.textContent = Math.max(0, current);
      badge.classList.toggle('d-none', current <= 0);
    });
  }

  // Quick "Add" buttons on product cards -> optimistic badge bump.
  document.querySelectorAll('.se-quick-add').forEach(function (form) {
    form.addEventListener('submit', function () {
      var qty = parseInt(form.querySelector('[name="quantity"]')?.value || '1', 10);
      updateCartBadge(qty);
    });
  });

  // Product gallery thumbnails.
  var mainImage = document.getElementById('mainProductImage');
  document.querySelectorAll('.se-thumb').forEach(function (thumb) {
    thumb.addEventListener('click', function () {
      document.querySelectorAll('.se-thumb').forEach(function (t) { t.classList.remove('active'); });
      thumb.classList.add('active');
      if (mainImage && thumb.dataset.imageUrl) {
        mainImage.src = thumb.dataset.imageUrl;
      }
    });
  });

  // Address selection cards.
  document.querySelectorAll('.se-address-card input[type="radio"]').forEach(function (radio) {
    radio.addEventListener('change', function () {
      document.querySelectorAll('.se-address-card').forEach(function (card) {
        card.classList.remove('selected');
      });
      radio.closest('.se-address-card').classList.add('selected');
    });
    if (radio.checked) radio.closest('.se-address-card').classList.add('selected');
  });

  // Dismiss alerts automatically after 6 seconds.
  document.querySelectorAll('.alert-dismissible').forEach(function (alertEl) {
    setTimeout(function () {
      if (window.bootstrap && bootstrap.Alert) {
        var instance = bootstrap.Alert.getOrCreateInstance(alertEl);
        instance.close();
      }
    }, 6000);
  });

  // Smooth scroll to reviews anchor.
  document.querySelectorAll('a[href^="#reviews"]').forEach(function (link) {
    link.addEventListener('click', function (e) {
      var target = document.querySelector(link.getAttribute('href'));
      if (target) { e.preventDefault(); target.scrollIntoView({ behavior: 'smooth' }); }
    });
  });

  // Global image-error fallback: any product/profile image that fails to load
  // (e.g. missing media file after a Render redeploy that wiped /media/) is
  // swapped to the bundled placeholder SVG so users never see a broken icon.
  var PLACEHOLDER_SRC = (window.SE_STATIC_URL || '/static/') + 'img/placeholder.svg';
  function installImgFallback(root) {
    (root || document).querySelectorAll('img').forEach(function (img) {
      if (img.dataset.seFallbackInstalled === '1') return;
      img.dataset.seFallbackInstalled = '1';
      img.addEventListener('error', function onErr() {
        if (img.getAttribute('src') === PLACEHOLDER_SRC) return;
        img.removeEventListener('error', onErr);
        img.setAttribute('src', PLACEHOLDER_SRC);
      });
      // If the image already errored before this handler was attached
      // (e.g. cached 404), swap it now.
      if (img.complete && img.naturalWidth === 0) {
        img.setAttribute('src', PLACEHOLDER_SRC);
      }
    });
  }
  installImgFallback(document);
  // Also cover images injected dynamically (quick-add cart refresh, etc.).
  if (window.MutationObserver) {
    new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        m.addedNodes.forEach(function (node) {
          if (node && node.querySelectorAll) installImgFallback(node);
        });
      });
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
})();
