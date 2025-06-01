document.addEventListener('DOMContentLoaded', () => {
  // Code block copy functionality
  const copyButtons = document.querySelectorAll('.copy-btn');
  
  copyButtons.forEach(button => {
    button.addEventListener('click', async () => {
      const codeBlock = button.previousElementSibling;
      const code = codeBlock.textContent;
      
      try {
        await navigator.clipboard.writeText(code);
        const originalText = button.textContent;
        button.textContent = 'Copied!';
        button.style.backgroundColor = '#4CAF50';
        
        setTimeout(() => {
          button.textContent = originalText;
          button.style.backgroundColor = '';
        }, 2000);
      } catch (err) {
        console.error('Failed to copy:', err);
        button.textContent = 'Failed!';
        button.style.backgroundColor = '#f44336';
        
        setTimeout(() => {
          button.textContent = originalText;
          button.style.backgroundColor = '';
        }, 2000);
      }
    });
  });

  // Highlight code blocks
  Prism.highlightAll();
});