(() => {
    const NS = window.StickyTableHeaders || (window.StickyTableHeaders = {});
    const registry = new Map(); // table -> StickyHeader

    const TABLE_SEL = ".data-table, .organization-data-table";
    const SCROLL_BOX_SEL = ".table-scroll, .distribution-table-scroll, .organization-table-wrapper";
    const ANCHOR_SEL = "[data-table-root], [data-table-section], .table-card, .card";

    const stickyTop = () => {
        const v = getComputedStyle(document.documentElement)
            .getPropertyValue("--table-sticky-top").trim();
        const n = parseFloat(v);
        return isFinite(n) ? n : 0;
    };

    class StickyHeader {
        constructor(table) {
            this.table  = table;
            this.thead  = table.querySelector("thead");
            if (!this.thead) return;

            this.floater    = null;   // div wrapper fixed-positioned
            this.floatTable = null;   // <table> inside floater
            this.floatThead = null;   // <thead> clone inside floatTable
            this.active     = false;

            this.scrollBox = table.closest(SCROLL_BOX_SEL);
            this.anchor    = table.closest(ANCHOR_SEL) || table.parentElement;

            this.tick   = this.tick.bind(this);
            this.resize = () => { this._synced = false; this.tick(); };

            window.addEventListener("scroll", this.tick,   {passive: true});
            window.addEventListener("resize", this.resize, {passive: true});
            this.scrollBox?.addEventListener("scroll", this.tick, {passive: true});

            this.tick();
        }

        /* ---------- floater construction ---------- */

        _buildFloater() {
            /* Outer clip div — sized to the VISIBLE part of the table */
            const floater = document.createElement("div");
            floater.className = "sticky-header-floater";
            floater.style.cssText = [
                "position:fixed",
                "z-index:50",
                "overflow:hidden",
                "visibility:hidden",
                "pointer-events:none",
                "margin:0",
                "padding:0",
                "box-sizing:border-box",
                "background:#ffffff",
            ].join(";");

            /* Inner <table> — same classes as original, fixed layout */
            const tbl = document.createElement("table");
            tbl.className = this.table.className;
            tbl.style.cssText = [
                "position:absolute",
                "top:0",
                "margin:0",
                "border-radius:0",
                "table-layout:fixed",
                "border-collapse:separate",
                "border-spacing:0",
                "box-sizing:border-box",
            ].join(";");

            /* Clone thead — keeps all classes/text */
            const thead = this.thead.cloneNode(true);
            tbl.appendChild(thead);
            floater.appendChild(tbl);
            document.body.appendChild(floater);

            /* Allow clicking sort buttons in the floater */
            floater.style.pointerEvents = "auto";
            const cloneBtns = [...thead.querySelectorAll("[data-sort-button]")];
            const realBtns  = [...this.thead.querySelectorAll("[data-sort-button]")];
            cloneBtns.forEach((btn, i) => {
                const real = realBtns[i];
                if (real) btn.addEventListener("click", () => real.click());
            });

            this.floater    = floater;
            this.floatTable = tbl;
            this.floatThead = thead;
        }

        /* ---------- sync geometry ---------- */

        _sync() {
            if (!this.floater) this._buildFloater();

            const top       = stickyTop();
            const tableRect = this.table.getBoundingClientRect();

            /* Clip region = intersection of table and its scroll container */
            const boxRect = this.scrollBox
                ? this.scrollBox.getBoundingClientRect()
                : tableRect;

            const clipLeft  = Math.max(tableRect.left,  boxRect.left);
            const clipRight = Math.min(tableRect.right, boxRect.right);
            const clipW     = Math.max(0, clipRight - clipLeft);

            /* Position the outer clip div */
            Object.assign(this.floater.style, {
                top    : top + "px",
                left   : clipLeft + "px",
                width  : clipW + "px",
            });

            /* The inner table shifts left so the right portion is visible */
            const innerLeft = tableRect.left - clipLeft;
            Object.assign(this.floatTable.style, {
                width : tableRect.width + "px",
                left  : innerLeft + "px",
            });

            /* Sync each th width from the REAL header cells */
            const realCells  = [...this.thead.querySelectorAll("tr:first-child > th")];
            const cloneCells = [...this.floatThead.querySelectorAll("tr:first-child > th")];
            realCells.forEach((cell, i) => {
                const clone = cloneCells[i];
                if (!clone) return;
                const w = cell.getBoundingClientRect().width;
                clone.style.width    = w + "px";
                clone.style.minWidth = w + "px";
                clone.style.maxWidth = w + "px";
                clone.style.boxSizing = "border-box";
            });

            /* Set floater height = thead height so clip works */
            this.floater.style.height = this.thead.offsetHeight + "px";
        }

        /* ---------- show / hide ---------- */

        _show() {
            this._sync();
            if (!this.active) {
                this.active = true;
                this.floater.style.visibility = "visible";
            }
        }

        _hide() {
            if (this.active) {
                this.active = false;
                if (this.floater) this.floater.style.visibility = "hidden";
            }
        }

        /* ---------- main update loop ---------- */

        tick() {
            if (!this.thead || !this.anchor) return;

            const top       = stickyTop();
            const theadRect = this.thead.getBoundingClientRect();
            const anchorRect = this.anchor.getBoundingClientRect();
            const theadH    = this.thead.offsetHeight;

            /* Stick when header scrolls past top, but table body still visible */
            const shouldStick =
                theadRect.top <= top + 0.5 &&
                anchorRect.bottom > top + theadH + 2;

            if (shouldStick) {
                this._show();
            } else {
                this._hide();
            }
        }

        /* Called when the table content is fully replaced (sort/filter reload) */
        refresh() {
            this.floater?.remove();
            this.floater    = null;
            this.floatTable = null;
            this.floatThead = null;
            this.active     = false;
            this.thead      = this.table.querySelector("thead");
            /* Re-wire scroll box in case the DOM section was swapped */
            this.scrollBox = this.table.closest(SCROLL_BOX_SEL);
            this.anchor    = this.table.closest(ANCHOR_SEL) || this.table.parentElement;
            this.tick();
        }

        destroy() {
            this.floater?.remove();
            window.removeEventListener("scroll",  this.tick);
            window.removeEventListener("resize",  this.resize);
            this.scrollBox?.removeEventListener("scroll", this.tick);
        }
    }

    /* ---------- public API ---------- */

    NS.bind = (table) => {
        if (!(table instanceof HTMLTableElement) || registry.has(table)) return;
        registry.set(table, new StickyHeader(table));
    };

    NS.unbind = (table) => {
        registry.get(table)?.destroy();
        registry.delete(table);
    };

    NS.rescan = (root = document) => {
        /* Clean up controllers whose tables left the DOM */
        for (const [tbl, ctrl] of registry) {
            if (!document.body.contains(tbl)) {
                ctrl.destroy();
                registry.delete(tbl);
            }
        }

        const scope = root instanceof Document ? document : root;
        scope.querySelectorAll?.(TABLE_SEL)?.forEach((tbl) => {
            if (registry.has(tbl)) {
                registry.get(tbl).refresh();
            } else {
                NS.bind(tbl);
            }
        });
    };

    /* ---------- boot ---------- */

    const init = () => NS.rescan(document);
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
