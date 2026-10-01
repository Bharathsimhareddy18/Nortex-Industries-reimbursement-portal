// Fades each section in when it scrolls into view, so the page reads in order.
// IntersectionObserver instead of a scroll listener: the browser tells us, we do not poll.
// Under reduced motion the CSS never hides .reveal, so this has no visible effect.
const observer = new IntersectionObserver((entries) => {
  for (const entry of entries) {
    if (entry.isIntersecting) {
      entry.target.classList.add("is-visible");
      observer.unobserve(entry.target);
    }
  }
}, { threshold: 0.15 });

document.querySelectorAll(".reveal").forEach((section) => observer.observe(section));
