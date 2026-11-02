const fs = require('fs');
let code = fs.readFileSync('hooks/useScreenShare.ts', 'utf8');

// Fix the setState callback - fix the entire block
const oldCode = `setState(prev => {
  return {
    ...prev,
    stream: newStream,
    tracks: {
      video: newTrack.kind === 'video' ? newTrack : prev.tracks.video,
      audio: newTrack.kind === 'audio' ? newTrack : prev.tracks.audio
    }
  };
}));`;

const newCode = `setState(prev => ({
  ...prev,
  stream: newStream,
  tracks: {
    video: newTrack.kind === 'video' ? newTrack : prev.tracks.video,
    audio: newTrack.kind === 'audio' ? newTrack : prev.tracks.audio
  }
}));`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('hooks/useScreenShare.ts', code);
  console.log('Fixed useScreenShare.ts - implicit return');
} else {
  console.log('Old code not found');
}