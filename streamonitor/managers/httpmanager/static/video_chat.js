const chatLoader = function(chatUrl){
  const chatContainer = document.getElementById('chat-messages');
  const video = document.getElementById('video');
  var chatElements = [];


  function updateChatVisibility(currentTime) {
    chatElements.forEach(chat => {
      if (chat.videoTime <= currentTime) {
        chat.element.classList.add('visible');
        chat.element.classList.remove('future');
      } else {
        chat.element.classList.remove('visible');
        chat.element.classList.add('future');
      }
    });

    const visibleMessages = chatElements.filter(c => c.element.classList.contains('visible'));
    if (visibleMessages.length > 3) {
      const lastVisible = visibleMessages[visibleMessages.length - 1].element;
      lastVisible.scrollIntoView({behavior: 'smooth', block: 'end'});
    } else {
      chatContainer.scrollTop = 0;
    }
  }

  async function loadChatMessages(chatUrl) {
    chatElements = [];
    chatContainer.textContent = '';
    const response = await fetch(chatUrl);
    const data = await response.json();
    data.forEach((entry, index) => {
      const div = document.createElement('tr');
      div.className = 'chat-message future';
      div.dataset.videoTime = entry.videoTime;
      div.innerHTML = `
        <td class="timestamp">${new Date(entry.realTime).toLocaleTimeString()}</td>
        <td class="username">${entry.username}</td>
        <td class="message">${entry.message}</td>
      `;
      chatContainer.appendChild(div);
      chatElements.push({element: div, videoTime: entry.videoTime});
    });

    video.addEventListener('timeupdate', async () => {
      updateChatVisibility(video.currentTime);
    });

    video.addEventListener('seeked', () => {
      updateChatVisibility(video.currentTime);
    });
  }
  loadChatMessages(chatUrl);
};