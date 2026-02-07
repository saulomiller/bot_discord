export class AudioReactiveBackground {
    constructor() {
        this.canvas = document.getElementById('liquid-canvas');
        this.ctx = this.canvas.getContext('2d');
        this.bars = [];
        this.isPlaying = false;
        this.currentVolume = 0.5;

        this.resizeCanvas();
        window.addEventListener('resize', () => this.resizeCanvas());
        this.animate();
    }

    resizeCanvas() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;

        const barCount = 64;
        this.bars = [];
        const barWidth = this.canvas.width / barCount;

        for (let i = 0; i < barCount; i++) {
            this.bars.push({
                x: i * barWidth,
                width: barWidth - 2,
                height: 0,
                targetHeight: 0,
                hue: (i / barCount) * 360,
                speed: 0.1 + Math.random() * 0.2
            });
        }
    }

    animate() {
        const backgroundGradient = this.ctx.createLinearGradient(0, 0, 0, this.canvas.height);
        backgroundGradient.addColorStop(0, 'rgba(10, 15, 35, 1)');
        backgroundGradient.addColorStop(0.5, 'rgba(20, 25, 50, 1)');
        backgroundGradient.addColorStop(1, 'rgba(10, 15, 35, 1)');

        this.ctx.fillStyle = backgroundGradient;
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        if (this.isPlaying) {
            const time = Date.now() * 0.002;
            for (let i = 0; i < this.bars.length; i++) {
                const positionFactor = i / this.bars.length;
                const beat = Math.sin(time * 2) * 0.2;
                const noise = Math.sin(time * 5 + i * 0.5) * Math.cos(time * 3 + i * 0.2);
                let amplitude = (1.0 - positionFactor * 0.5) * 0.8;
                let value = Math.max(0, amplitude + noise * 0.3 + beat);
                this.bars[i].targetHeight = value * this.canvas.height * 0.4 * (this.currentVolume + 0.5);
            }
        } else {
            for (let bar of this.bars) {
                bar.targetHeight = 5;
            }
        }

        this.drawBars();
        requestAnimationFrame(() => this.animate());
    }

    drawBars() {
        const centerY = this.canvas.height * 0.5;
        const smoothing = 0.2;

        for (let bar of this.bars) {
            bar.height = bar.height * (1 - smoothing) + bar.targetHeight * smoothing;

            const gradient = this.ctx.createLinearGradient(
                bar.x, centerY - bar.height,
                bar.x, centerY
            );

            gradient.addColorStop(0, `hsla(${bar.hue}, 100%, 65%, 0.8)`);
            gradient.addColorStop(1, `hsla(${bar.hue}, 100%, 45%, 0.2)`);

            this.ctx.fillStyle = gradient;
            this.ctx.fillRect(bar.x, centerY - bar.height, bar.width, bar.height);

            const gradientReflect = this.ctx.createLinearGradient(
                bar.x, centerY,
                bar.x, centerY + bar.height
            );

            gradientReflect.addColorStop(0, `hsla(${bar.hue}, 100%, 45%, 0.2)`);
            gradientReflect.addColorStop(1, `hsla(${bar.hue}, 100%, 20%, 0)`);

            this.ctx.fillStyle = gradientReflect;
            this.ctx.fillRect(bar.x, centerY, bar.width, bar.height);
        }

        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
        this.ctx.beginPath();
        this.ctx.moveTo(0, centerY);
        this.ctx.lineTo(this.canvas.width, centerY);
        this.ctx.stroke();
    }

    syncPlayState(isPlaying, volume = 0.5) {
        this.isPlaying = isPlaying;
        if (volume) this.currentVolume = volume;
    }
}
