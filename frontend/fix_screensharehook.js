const fs = require('fs');
let code = fs.readFileSync('hooks/useScreenShare.ts', 'utf8');

// Fix the setState callback - use explicit return
const oldCode = `setState(prev => {
        const videoTrack = newTrack.kind === 'video' ? newTrack : prev.tracks.video;
        const audioTrack = newTrack.kind === 'audio' ? newTrack : prev.tracks.audio;
        const tracks = { video: videoTrack, audio: audioTrack };
        return Object.assign({}, prev, { stream: newStream, tracks });
      });`;

const newCode = `setState(prev => {
        const videoTrack = newTrack.kind === 'video' ? newTrack : prev.tracks.video;
        const audioTrack = newTrack.kind === 'audio' ? newTrack : prev.tracks.audio;
        return Object.assign({}, prev, {
          stream: newStream,
          tracks: { video: videoTrack, audio: audioTrack }
        });
      });`;

if (code.includes(oldCode)) {
  code = code.replace(oldCode, newCode);
  fs.writeFileSync('hooks/useScreenShare.ts', code);
  console.log('Fixed useScreenShare.ts');
} else {
  console.log('Old code not found');
}