document.addEventListener('DOMContentLoaded', () => {
    const logOutput = document.getElementById('log-output');
    let isScrolledToBottom = true;

    // Check if user has scrolled up to prevent auto-scrolling
    logOutput.addEventListener('scroll', () => {
        isScrolledToBottom = logOutput.scrollHeight - logOutput.clientHeight <= logOutput.scrollTop + 1;
    });

    // Connect to the log stream endpoint using Server-Sent Events
    const eventSource = new EventSource('/admin/log-stream');

    eventSource.onopen = () => {
        logOutput.textContent = 'Connection established. Waiting for logs...\n';
    };

    eventSource.onmessage = (event) => {
        // Append the new log line and add a newline character
        logOutput.textContent += event.data + '\n';

        // Auto-scroll to the bottom if the user hasn't scrolled up
        if (isScrolledToBottom) {
            logOutput.scrollTop = logOutput.scrollHeight;
        }
    };

    eventSource.onerror = () => {
        logOutput.textContent += '\n--- Connection lost. Attempting to reconnect... ---\n';
        eventSource.close();
    };
});
