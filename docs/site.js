(function () {
  var cfg = window.MARVIN_SITE || {};
  var payUrl = cfg.paymentLinkUrl || "";
  var downloadUrl =
    cfg.downloadUrl ||
    "https://github.com/RizzyRoger/marvin/archive/refs/heads/main.zip";

  document.querySelectorAll('[data-role="payment"]').forEach(function (el) {
    if (payUrl) {
      el.setAttribute("href", payUrl);
      el.setAttribute("rel", "noopener noreferrer");
    } else {
      el.addEventListener("click", function (e) {
        e.preventDefault();
        alert(
          "Stripe Payment Link is not configured yet. Set paymentLinkUrl in config.js."
        );
      });
    }
  });

  var dl = document.getElementById("download-link");
  if (dl) {
    dl.setAttribute("href", downloadUrl);
  }

  if (window.location.search.indexOf("paid=1") !== -1) {
    var h = document.getElementById("download-headline");
    var l = document.getElementById("download-lede");
    if (h) h.textContent = "Thank you — download Marvin";
    if (l) {
      l.textContent =
        "Your payment went through. Grab the current build below.";
    }
  }
})();
