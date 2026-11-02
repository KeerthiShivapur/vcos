const fs = require('fs');
let code = fs.readFileSync('hooks/useScreenShare.ts', 'utf8');

// Fix the setState callback - inline everything
const oldCode = `setState(function(prev) {
        const videoTrack = newTrack.kind === 'video' ? newTrack : prev.tracks.video;
        const audioTrack = newTrack.kind === 'audio' ? newTrack : prev.tracks.audio;
        return { ...prev, stream: newStream, tracks: { video: videoTrack, audio: audioTrack } };
      });`;

const newCode = `setState(function(prev) {
        return { 
          ...prev, 
          stream: newStream, 
          tracks: { 
            video: newTrack.kind === 'video' ? newTrack : prev.tracks.video,
            audio: newTrack.kind === 'audio' ? newTrack : prev.tracks.audio
          } 
        };
      });`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('hooks/useScreenShare.ts', code);
  console.log('Fixed useScreenShare.ts - fully inlined');
} else {
  console.log('Old code not found');
}