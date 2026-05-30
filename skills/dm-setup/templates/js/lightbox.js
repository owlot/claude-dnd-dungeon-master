document.addEventListener('click', e => {
  const img = e.target.closest('.scene-img, .card-portrait, .card-place');
  if (!img) return;
  document.getElementById('lightbox-img').src = img.src;
  document.getElementById('lightbox-img').alt = img.alt;
  document.getElementById('lightbox').classList.add('open');
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') document.getElementById('lightbox').classList.remove('open');
});
