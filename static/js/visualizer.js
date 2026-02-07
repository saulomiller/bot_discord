export class AudioReactiveBackground {
    constructor() {
        try {
            this.canvas = document.getElementById('liquid-canvas');
            if (!this.canvas) throw new Error('Canvas element not found');

            this.ctx = this.canvas.getContext('2d');
            this.bars = [];
            this.isPlaying = false;
            this.currentVolume = 0.5;

            this.resizeCanvas();
            window.addEventListener('resize', () => this.resizeCanvas());
            this.animate();
            console.log('AudioReactiveBackground initialized');
        } catch (e) {
            console.error('AudioReactiveBackground error:', e);
        }
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
                // Cores da GUI: azul (210°) a ciano (180°) a roxo (270°)
                hue: 180 + (i / barCount) * 90, // 180° a 270° (ciano → azul → roxo)
                speed: 0.1 + Math.random() * 0.2,
                phase: Math.random() * Math.PI * 2 // Fase aleatória para ondas
            });
        }
    }

    animate() {
        // Gradiente de fundo mais escuro e sutil
        const backgroundGradient = this.ctx.createLinearGradient(0, 0, 0, this.canvas.height);
        backgroundGradient.addColorStop(0, 'rgba(10, 15, 35, 1)');
        backgroundGradient.addColorStop(0.5, 'rgba(15, 20, 45, 1)');
        backgroundGradient.addColorStop(1, 'rgba(10, 15, 35, 1)');

        this.ctx.fillStyle = backgroundGradient;
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        if (this.isPlaying) {
            // Modo tocando: animação energética mas no ritmo
            const time = Date.now() * 0.0008; // Reduzido de 0.002 para 0.0008 (60% mais lento)
            for (let i = 0; i < this.bars.length; i++) {
                const positionFactor = i / this.bars.length;
                // Beat mais lento e pronunciado (como batida de música)
                const beat = Math.sin(time * 1.2) * 0.3; // Reduzido de 2 para 1.2
                // Variação mais suave
                const noise = Math.sin(time * 2.5 + i * 0.5) * Math.cos(time * 1.5 + i * 0.2); // Reduzido
                let amplitude = (1.0 - positionFactor * 0.5) * 0.8;
                let value = Math.max(0, amplitude + noise * 0.2 + beat); // Reduzido noise de 0.3 para 0.2
                this.bars[i].targetHeight = value * this.canvas.height * 0.4 * (this.currentVolume + 0.5);
            }
        } else {
            // Modo idle: ondas suaves e lentas
            const time = Date.now() * 0.0003; // Reduzido de 0.0005 para 0.0003 (40% mais lento)
            for (let i = 0; i < this.bars.length; i++) {
                const positionFactor = i / this.bars.length;
                // Onda senoidal suave que percorre as barras
                const wave1 = Math.sin(time * 1.5 + positionFactor * Math.PI * 2 + this.bars[i].phase); // Reduzido de 2 para 1.5
                const wave2 = Math.sin(time * 1.0 - positionFactor * Math.PI * 3); // Reduzido de 1.5 para 1.0
                const combined = (wave1 * 0.6 + wave2 * 0.4);
                // Altura entre 15% e 35% da tela
                this.bars[i].targetHeight = (0.15 + combined * 0.1) * this.canvas.height;
            }
        }

        this.drawBars();
        requestAnimationFrame(() => this.animate());
    }

    drawBars() {
        const centerY = this.canvas.height * 0.5;
        const smoothing = this.isPlaying ? 0.2 : 0.05; // Mais suave quando idle

        for (let bar of this.bars) {
            bar.height = bar.height * (1 - smoothing) + bar.targetHeight * smoothing;

            // Cores da GUI com saturação ajustada
            const saturation = this.isPlaying ? 100 : 70; // Menos saturado quando idle
            const lightness = this.isPlaying ? 65 : 55; // Mais escuro quando idle
            const alpha = this.isPlaying ? 0.8 : 0.5; // Mais transparente quando idle

            const gradient = this.ctx.createLinearGradient(
                bar.x, centerY - bar.height,
                bar.x, centerY
            );

            gradient.addColorStop(0, `hsla(${bar.hue}, ${saturation}%, ${lightness}%, ${alpha})`);
            gradient.addColorStop(1, `hsla(${bar.hue}, ${saturation}%, ${lightness - 20}%, ${alpha * 0.3})`);

            this.ctx.fillStyle = gradient;
            this.ctx.fillRect(bar.x, centerY - bar.height, bar.width, bar.height);

            // Reflexo
            const gradientReflect = this.ctx.createLinearGradient(
                bar.x, centerY,
                bar.x, centerY + bar.height
            );

            gradientReflect.addColorStop(0, `hsla(${bar.hue}, ${saturation}%, ${lightness - 20}%, ${alpha * 0.3})`);
            gradientReflect.addColorStop(1, `hsla(${bar.hue}, ${saturation}%, 20%, 0)`);

            this.ctx.fillStyle = gradientReflect;
            this.ctx.fillRect(bar.x, centerY, bar.width, bar.height);
        }

        // Linha central mais sutil
        this.ctx.strokeStyle = this.isPlaying ? 'rgba(255, 255, 255, 0.15)' : 'rgba(255, 255, 255, 0.08)';
        this.ctx.lineWidth = 1;
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

