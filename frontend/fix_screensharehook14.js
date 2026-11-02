const fs = require('fs');
let code = fs.readFileSync('hooks/useScreenShare.ts', 'utf8');

// Fix the setState callback - use a completely different approach
const oldCode = `setState(prev => {
  return { 
    ...prev, 
    stream: newStream, 
    tracks: { 
      video: newTrack.kind === 'video' ? newTrack : prev.tracks.video,
      audio: newTrack.kind === 'audio' ? newTrack : prev.tracks.audio
    }
  };
});`;

const newCode = `setState(prev => {
  const updated = { 
    ...prev, 
    stream: newStream, 
    tracks: { 
      video: newTrack.kind === 'video' ? newTrack : prev.tracks.video,
      audio: newTrack.kind === 'audio' ? newTrack : prev.tracks.audio
    }
  };
  return updated;
});`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('hooks/useScreenShare.ts', code);
  console.log('Fixed useScreenShare.ts - variable for return');
} else {
  console.log('Old code not found');
}