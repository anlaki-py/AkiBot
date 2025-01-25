// Mobile menu handling
document.querySelector('.mobile-menu-btn').addEventListener('click', function() {
  document.querySelector('.nav-links').classList.toggle('show');
});

// Smooth scrolling for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function (e) {
    e.preventDefault();
    document.querySelector(this.getAttribute('href')).scrollIntoView({
      behavior: 'smooth'
    });
  });
});

// Code copy functionality
document.querySelectorAll('.copy-btn').forEach(button => {
  button.addEventListener('click', async function() {
    const codeBlock = this.parentElement.querySelector('code');
    const text = codeBlock.textContent;
    
    try {
      await navigator.clipboard.writeText(text);
      
      // Visual feedback
      const icon = this.querySelector('i');
      icon.dataset.feather = 'check';
      this.classList.add('copied');
      feather.replace();
      
      // Reset after 2 seconds
      setTimeout(() => {
        icon.dataset.feather = 'copy';
        this.classList.remove('copied');
        feather.replace();
      }, 2000);
    } catch (err) {
      console.error('Failed to copy text:', err);
    }
  });
});

// Intersection Observer for fade-in animations
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('show');
    }
  });
}, {
  threshold: 0.1
});

document.querySelectorAll('.feature-card, .feature-item, .step').forEach((el) => {
  observer.observe(el);
});