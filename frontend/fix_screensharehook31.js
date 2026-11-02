const fs = require('fs');
let code = fs.readFileSync('hooks/useScreenShare.ts', 'utf8');

// Fix the replaceTrack function - rewrite with proper formatting using regex
const regex = /const replaceTrack = useCallback\(async \(newTrack: MediaStreamTrack\) => \{[\s\S]*?\}, \[state\.stream\]\);/;

const newCode = `const replaceTrack = useCallback(async (newTrack: MediaStreamTrack) => {
    // In a real implementation, this would replace the track in the WebRTC peer connection
    // For now, we just update the local stream
    if (state.stream) {
      const newStream = new MediaStream();
      
      // Add all existing tracks except the one being replaced
      state.stream.getTracks().forEach(track => {
        if (track.kind !== newTrack.kind) {
          newStream.addTrack(track.clone());
        }
      });
      
      // Add the new track
      newStream.addTrack(newTrack);
      
      setState(prev => ({
        ...prev,
        stream: newStream,
        tracks: {
          video: newTrack.kind === 'video' ? newTrack : prev.tracks.video,
          audio: newTrack.kind === 'audio' ? newTrack : prev.tracks.audio
        }
      }));
    }
  }, [state.stream]);`;

const match = code.match(regex);
if (match) {
  code = code.replace(regex, newCode);
  fs.writeFileSync('hooks/useScreenShare.ts', code);
  console.log('Fixed useScreenShare.ts - replaceTrack function (regex)');
} else {
  console.log('Pattern not found');
}