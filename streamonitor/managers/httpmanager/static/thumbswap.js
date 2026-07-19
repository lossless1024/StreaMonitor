(function () {
    // Replace a placeholder <img> with the real thumbnail on 2xx, or the error
    // placeholder on 5xx. Used as: hx-on::after-request="thumbSwap(this, event, '<realUrl>')"
    window.thumbSwap = function (el, ev, realUrl) {
        var status = ev && ev.detail && ev.detail.xhr ? ev.detail.xhr.status : 0;
        var target = null;
        if (status >= 200 && status < 300) target = realUrl;
        else if (status >= 500) target = '/static/placeholders/error.jpg';
        if (target === null) return;
        var img = document.createElement('img');
        for (var i = 0; i < el.attributes.length; i++) {
            var a = el.attributes[i];
            if (a.name.indexOf('hx-') === 0) continue;
            if (a.name === 'src') continue;
            img.setAttribute(a.name, a.value);
        }
        img.src = target;
        el.replaceWith(img);
    };
})();
