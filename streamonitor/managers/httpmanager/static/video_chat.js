const chatLoader = function (chatUrl) {
  const chatBox = document.getElementById('chat-container');
  const chatMessages = document.getElementById('chat-messages');
  const video = document.getElementById('video');
  let chatElements = [];
  let lastScrollTarget = null;

  // Scroll only the chat box. scrollIntoView() must not be used here: it
  // scrolls every scrollable ancestor, yanking the whole page to the top.
  function scrollChatTo(element, behavior) {
    if (element === lastScrollTarget) return;
    lastScrollTarget = element;
    const boxRect = chatBox.getBoundingClientRect();
    const elRect = element.getBoundingClientRect();
    chatBox.scrollTo({
      top: chatBox.scrollTop + (elRect.bottom - boxRect.bottom),
      behavior: behavior
    });
  }

  function updateChatVisibility(currentTime, behavior) {
    let lastVisible = null;
    chatElements.forEach(chat => {
      const visible = chat.videoTime <= currentTime;
      chat.element.classList.toggle('visible', visible);
      chat.element.classList.toggle('future', !visible);
      if (visible) lastVisible = chat.element;
    });

    if (lastVisible) {
      // Keep up to 3 upcoming messages peeking below the newest one
      let target = lastVisible;
      for (let i = 0; i < 3; i++) if (target.nextElementSibling) target = target.nextElementSibling;
      scrollChatTo(target, behavior);
    } else {
      lastScrollTarget = null;
      chatBox.scrollTo({top: 0, behavior: behavior});
    }
  }

  async function loadChatMessages() {
    chatElements = [];
    chatMessages.textContent = '';
    let data = [];
    try {
      const response = await fetch(chatUrl);
      if (response.ok) data = await response.json();
    } catch (e) {
      data = [];
    }

    // No chat log for this video: hide the whole column so the video
    // can use the full width, instead of showing an empty box
    const chatColumn = chatBox.closest('.chat-column') || chatBox;
    chatColumn.classList.toggle('no-chat', data.length === 0);
    if (data.length === 0) return;

    data.forEach(entry => {
      const row = document.createElement('tr');
      row.className = 'chat-message future';
      row.dataset.videoTime = entry.videoTime;
      const timestamp = document.createElement('td');
      timestamp.className = 'timestamp';
      timestamp.textContent = new Date(entry.realTime).toLocaleTimeString();
      const username = document.createElement('td');
      username.className = 'username';
      username.textContent = entry.username;
      const message = document.createElement('td');
      message.className = 'message';
      // textContent, not innerHTML: chat is untrusted viewer input
      message.textContent = entry.message;
      row.append(timestamp, username, message);
      chatMessages.appendChild(row);
      chatElements.push({element: row, videoTime: entry.videoTime});
    });

    updateChatVisibility(video.currentTime, 'auto');

    video.addEventListener('timeupdate', () => {
      updateChatVisibility(video.currentTime, 'smooth');
    });

    video.addEventListener('seeked', () => {
      lastScrollTarget = null;  // force a re-sync even onto the same target
      updateChatVisibility(video.currentTime, 'auto');
    });
  }
  loadChatMessages();
};
