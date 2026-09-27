import type { Plugin, VisualElement } from 'chart.js';

/** Show the count that follows legend filtering and legible shares on larger slices. */
export function doughnutInsightPlugin(id: string, values: number[], totalLabel: string, dark: boolean): Plugin<'doughnut'> {
    return {
        id,
        afterDraw(chart) {
            const { ctx, chartArea } = chart;
            if (!chartArea) return;
            const visibleTotal = values.reduce((sum, value, index) => sum + (chart.getDataVisibility(index) ? value : 0), 0);
            const centerX = (chartArea.left + chartArea.right) / 2;
            const centerY = (chartArea.top + chartArea.bottom) / 2;
            ctx.save();
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = dark ? '#94a3b8' : '#64748b';
            ctx.font = '600 11px sans-serif';
            ctx.fillText(totalLabel, centerX, centerY - 7);
            ctx.fillStyle = dark ? '#e2e8f0' : '#1e293b';
            ctx.font = '700 17px sans-serif';
            ctx.fillText(visibleTotal.toLocaleString(), centerX, centerY + 15);
            if (visibleTotal > 0) {
                ctx.fillStyle = '#fff';
                ctx.font = '600 11px sans-serif';
                chart.getDatasetMeta(0).data.forEach((arc, index) => {
                    if (!chart.getDataVisibility(index)) return;
                    const share = values[index] / visibleTotal;
                    if (share < 0.08) return;
                    const { x, y } = (arc as unknown as VisualElement).getCenterPoint();
                    if (x !== null && y !== null) ctx.fillText(`${Math.round(share * 100)}%`, x, y);
                });
            }
            ctx.restore();
        },
    };
}
