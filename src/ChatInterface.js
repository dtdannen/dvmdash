import React, { useState, useEffect } from 'react';
import { MessageList, Input } from 'react-chat-elements';
import 'react-chat-elements/dist/main.css';
import NDK, { NDKEvent, NDKNip07Signer } from '@nostr-dev-kit/ndk';

const ChatInterface = () => {
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [ndk, setNdk] = useState(null);
  const [signer, setSigner] = useState(null);
  const [userProfile, setUserProfile] = useState(null);

  useEffect(() => {
    initNostr();
  }, []);

  const initNostr = async () => {
    try {
      const nip07signer = new NDKNip07Signer();
      const ndkInstance = new NDK({
        explicitRelayUrls: [
          'wss://nostr-pub.wellorder.net',
          'wss://relay.damus.io',
          'wss://nos.lol',
          'wss://relay.primal.net',
          'wss://offchain.pub',
          'wss://nostr.mom',
          'wss://relay.nostr.bg',
          'wss://nostr.oxtr.dev',
          'wss://nostr-relay.nokotaro.com',
          'wss://relay.nostr.wirednet.jp',
          'localhost:4736',
        ],
        signer: nip07signer
      });

      await ndkInstance.connect();
      setNdk(ndkInstance);

      const user = await nip07signer.user();
      if (user.npub) {
        setSigner(nip07signer);
        const profile = await user.fetchProfile();
        setUserProfile(profile);
      }

      startListeningForEvents(ndkInstance);
    } catch (error) {
      console.error('Error initializing Nostr:', error);
    }
  };

  const startListeningForEvents = (ndkInstance) => {
    const filter = { kinds: [5050, 6050, 7000] };
    const subscription = ndkInstance.subscribe(filter);

    subscription.on("event", (event) => {
      const newMessage = {
        position: 'left',
        type: 'text',
        text: `${event.pubkey.slice(0, 8)}: ${event.content}`,
        date: new Date(event.created_at * 1000),
      };
      setMessages(prevMessages => [...prevMessages, newMessage]);
    });
  };

  const sendEvent = async () => {
    if (!inputText.trim() || !ndk || !signer) return;

    try {
      const event = new NDKEvent(ndk);
      event.kind = 5050;
      event.content = inputText;

      await event.sign(signer);
      await ndk.publish(event);

      const newMessage = {
        position: 'right',
        type: 'text',
        text: inputText,
        date: new Date(),
      };
      setMessages(prevMessages => [...prevMessages, newMessage]);
      setInputText('');
    } catch (error) {
      console.error('Failed to publish event:', error);
    }
  };

  return (
    <div className="chat-container">
      <MessageList
        className="message-list"
        lockable={true}
        toBottomHeight={'100%'}
        dataSource={messages}
      />
      <Input
        placeholder="Type here..."
        value={inputText}
        onChange={(e) => setInputText(e.target.value)}
        rightButtons={
          <button onClick={sendEvent}>Send</button>
        }
      />
    </div>
  );
};

export default ChatInterface;