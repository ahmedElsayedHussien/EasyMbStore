// سلة المبيعات
let cart = [];
let allDevices = [];
let allStocks = [];

// استيراد بيانات الأجهزة عند تحميل الصفحة
document.addEventListener("DOMContentLoaded", () => {
    const jsonContainer = document.getElementById("devices-data-json");
    if (jsonContainer) {
        try {
            allDevices = JSON.parse(jsonContainer.textContent);
        } catch (e) {
            console.error("فشل قراءة بيانات السيريالات المتاحة:", e);
        }
    }

    const stocksContainer = document.getElementById("stocks-data-json");
    if (stocksContainer) {
        try {
            allStocks = JSON.parse(stocksContainer.textContent);
        } catch (e) {
            console.error("فشل قراءة بيانات المخزون المتاحة:", e);
        }
    }

    // تهيئة مستمع قارئ الباركود والسيريال
    const scannerInput = document.getElementById("barcode-scanner");
    if (scannerInput) {
        scannerInput.addEventListener("keypress", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                handleBarcodeScan(scannerInput.value);
            }
        });
    }

    // البحث في المنتجات محلياً بالاسم
    const searchInput = document.getElementById("product-search");
    if (searchInput) {
        searchInput.addEventListener("input", () => {
            const query = searchInput.value.toLowerCase();
            document.querySelectorAll(".product-card-container").forEach(card => {
                const name = card.dataset.name.toLowerCase();
                const barcode = card.dataset.barcode.toLowerCase();
                if (name.includes(query) || barcode.includes(query)) {
                    card.style.display = "block";
                } else {
                    card.style.display = "none";
                }
            });
        });
    }

    // ربط تغيير طرق الدفع بالرقم المرجعي للمعاملة وتحديث الكاش تلقائياً
    const cashInput = document.getElementById("pay-cash");
    const visaInput = document.getElementById("pay-visa");
    const walletInput = document.getElementById("pay-wallet");
    const transSection = document.getElementById("transaction-id-section");

    const toggleTransSection = () => {
        const visa = parseFloat(visaInput.value) || 0;
        const wallet = parseFloat(walletInput.value) || 0;
        if (visa > 0 || wallet > 0) {
            transSection.classList.remove("d-none");
        } else {
            transSection.classList.add("d-none");
        }
    };

    const adjustPaymentDistribution = () => {
        const net = parseFloat(document.getElementById("summary-net").textContent) || 0;
        let visa = parseFloat(visaInput.value) || 0;
        let wallet = parseFloat(walletInput.value) || 0;

        // منع تلاعب إجمالي المدفوعات وتجاوزه لصافي الفاتورة
        if (visa > net) {
            visa = net;
            visaInput.value = visa.toFixed(2);
        }
        if (wallet > net - visa) {
            wallet = net - visa;
            walletInput.value = wallet.toFixed(2);
        }
        if (visa > net - wallet) {
            visa = net - wallet;
            visaInput.value = visa.toFixed(2);
        }

        const remaining = Math.max(0, net - visa - wallet);
        cashInput.value = remaining.toFixed(2);
        toggleTransSection();
    };

    if (visaInput && walletInput && cashInput) {
        visaInput.addEventListener("input", adjustPaymentDistribution);
        walletInput.addEventListener("input", adjustPaymentDistribution);
    }

    // ربط اختيار جهاز الاستبدال بملء قيمة الاستبدال تلقائياً
    const tradeInSelect = document.getElementById("trade-in-device-select");
    const tradeInValInput = document.getElementById("trade-in-value");
    if (tradeInSelect && tradeInValInput) {
        tradeInSelect.addEventListener("change", () => {
            const selectedOpt = tradeInSelect.options[tradeInSelect.selectedIndex];
            if (selectedOpt && selectedOpt.value) {
                const cost = parseFloat(selectedOpt.dataset.cost) || 0;
                tradeInValInput.value = cost.toFixed(2);
            } else {
                tradeInValInput.value = "0.00";
            }
            calculateInvoiceTotals();
        });
    }
});

// التعامل مع مسح الباركود
function handleBarcodeScan(code) {
    if (!code.trim()) return;
    
    // التعرف التلقائي على بطاقة الهدية (10 أحرف هيكس)
    if (code.length === 10 && /^[0-9A-F]+$/i.test(code)) {
        const scannerInput = document.getElementById("barcode-scanner");
        if (scannerInput) scannerInput.value = ""; 
        
        const giftInput = document.getElementById("gift-card-input");
        if (giftInput) {
            giftInput.value = code.toUpperCase();
            if (typeof verifyGiftCard === 'function') {
                verifyGiftCard();
            }
        }
        return;
    }
    
    fetch(`/pos/search/?code=${encodeURIComponent(code)}`)
        .then(res => res.json())
        .then(data => {
            const scannerInput = document.getElementById("barcode-scanner");
            if (scannerInput) scannerInput.value = ""; // تفريغ الخانة فورا

            if (data.found) {
                if (data.is_serialized) {
                    // إذا كان جهاز مسيرل ممسوح بالـ IMEI مباشرة
                    addProductToCart(data.product_id || data.id, data.name, data.price, true, data.device_id, data.warehouse_id, data.imei);
                } else {
                    // إذا كان صنف سائب ممسوح بالباركود
                    addProductToCart(data.id, data.name, data.price, false);
                }
            } else {
                alert("الباركود أو السيريال غير مسجل بالنظام أو مباع مسبقاً.");
            }
        })
        .catch(err => {
            console.error("خطأ أثناء الاستعلام عن الباركود:", err);
        });
}

// إضافة منتج للسلة
function addProductToCart(productId, productName, price, requiresImei, deviceId = null, warehouseId = null, imei = "", condition = null) {
    // تحديد المخزن الافتراضي بناءً على التوفر
    let selectedWh = warehouseId;
    if (!selectedWh) {
        if (requiresImei) {
            // للهواتف المسيرنة: نختار مخزن أول جهاز متاح للبيع لهذا المنتج وطبقاً للشرط
            const firstDevice = allDevices.find(d => d.product_id === productId && (!condition || d.condition === condition));
            if (firstDevice) {
                selectedWh = firstDevice.warehouse_id;
                deviceId = firstDevice.id;
                imei = firstDevice.imei;
            }
        } else {
            // للمنتجات السائبة: نختار أول مخزن يحتوي على رصيد متاح
            const stockObj = allStocks.find(s => s.product_id === productId && s.quantity > 0);
            if (stockObj) {
                selectedWh = stockObj.warehouse_id;
            }
        }
    }

    if (!selectedWh) {
        selectedWh = document.getElementById("warehouse-select-default") ? document.getElementById("warehouse-select-default").value : 1;
    }

    if (requiresImei) {
        cart.push({
            product_id: productId,
            name: productName,
            price: price,
            requires_imei: true,
            warehouse_id: parseInt(selectedWh),
            quantity: 1,
            device_id: deviceId ? parseInt(deviceId) : null,
            imei: imei,
            condition: condition
        });
    } else {
        const existing = cart.find(item => item.product_id === productId && item.warehouse_id === parseInt(selectedWh) && !item.requires_imei);
        if (existing) {
            existing.quantity += 1;
        } else {
            cart.push({
                product_id: productId,
                name: productName,
                price: price,
                requires_imei: false,
                warehouse_id: parseInt(selectedWh),
                quantity: 1,
                device_id: null,
                imei: ""
            });
        }
    }
    
    renderCart();
}

// حذف عنصر من السلة
function removeCartItem(index) {
    cart.splice(index, 1);
    renderCart();
}

// تعديل كمية المنتجات السائبة
function updateCartItemQty(index, qty) {
    if (qty < 1) qty = 1;
    cart[index].quantity = parseInt(qty);
    calculateInvoiceTotals();
}

// تعديل مخزن العنصر
function updateCartItemWarehouse(index, warehouseId) {
    cart[index].warehouse_id = parseInt(warehouseId);
    
    if (cart[index].requires_imei) {
        cart[index].device_id = null;
        cart[index].imei = "";
    }
    renderCart();
}

// ربط الجهاز المختار بـ IMEI محدد وتعديل المخزن آلياً
function updateCartItemDevice(index, selectElement) {
    const deviceId = parseInt(selectElement.value);
    if (deviceId) {
        cart[index].device_id = deviceId;
        const fullText = selectElement.options[selectElement.selectedIndex].text;
        const imeiClean = fullText.split(' (')[0];
        cart[index].imei = imeiClean;
        
        // تعيين المخزن المرتبط بالجهاز آلياً
        const deviceObj = allDevices.find(d => d.id === deviceId);
        if (deviceObj) {
            cart[index].warehouse_id = deviceObj.warehouse_id;
        }
    } else {
        cart[index].device_id = null;
        cart[index].imei = "";
    }
    renderCart();
}

// رندرة السلة في الواجهة
function renderCart() {
    const container = document.getElementById("cart-items-container");
    
    if (cart.length === 0) {
        container.innerHTML = `
            <div class="text-center text-secondary py-5" id="cart-empty-message">
                <i class="bi bi-basket3 fs-1 d-block mb-3"></i>
                السلة فارغة، امسح باركود المنتج أو اضغط عليه لإضافته.
            </div>
        `;
        calculateInvoiceTotals();
        return;
    }
    
    container.innerHTML = "";

    const warehouseOptions = Array.from(document.querySelectorAll("#warehouse-options-hidden option")).map(opt => ({
        id: parseInt(opt.value),
        name: opt.textContent
    }));

    cart.forEach((item, idx) => {
        const itemRow = document.createElement("div");
        itemRow.className = "pos-cart-item";
        
        // تصفية المستودعات المتاحة التي يوجد بها رصيد أو أجهزة لهذا الصنف فقط
        let allowedWarehouses = [];
        if (item.requires_imei) {
            const productDevices = allDevices.filter(d => d.product_id === item.product_id);
            const whIds = new Set(productDevices.map(d => d.warehouse_id));
            if (item.warehouse_id) whIds.add(item.warehouse_id);
            allowedWarehouses = warehouseOptions.filter(wh => whIds.has(wh.id));
        } else {
            const productStocks = allStocks.filter(s => s.product_id === item.product_id && s.quantity > 0);
            const whIds = new Set(productStocks.map(s => s.warehouse_id));
            if (item.warehouse_id) whIds.add(item.warehouse_id);
            allowedWarehouses = warehouseOptions.filter(wh => whIds.has(wh.id));
        }
        if (allowedWarehouses.length === 0) {
            allowedWarehouses = warehouseOptions;
        }

        let warehouseSelectHTML = `<select class="form-select form-select-sm mt-1" disabled onchange="updateCartItemWarehouse(${idx}, this.value)">`;
        allowedWarehouses.forEach(wh => {
            warehouseSelectHTML += `<option value="${wh.id}" ${item.warehouse_id === wh.id ? 'selected' : ''}>${wh.name}</option>`;
        });
        warehouseSelectHTML += `</select>`;

        let imeiSelectHTML = "";
        if (item.requires_imei) {
            // جلب الأجهزة المتاحة لهذا الموديل في كل المستودعات لتسهيل الاختيار وطبقاً للشرط
            const availableForProduct = allDevices.filter(d => d.product_id === item.product_id && (!item.condition || d.condition === item.condition));
            
            imeiSelectHTML = `<select class="form-select form-select-sm mt-2 text-info border-info" onfocus="refreshIMEIDropdown(${idx}, this)" onchange="updateCartItemDevice(${idx}, this)">`;
            imeiSelectHTML += `<option value="">-- اختر السيريال IMEI --</option>`;
            
            if (item.device_id && !availableForProduct.some(d => d.id === item.device_id)) {
                imeiSelectHTML += `<option value="${item.device_id}" selected>${item.imei}</option>`;
            }
            
            availableForProduct.forEach(d => {
                const whName = warehouseOptions.find(w => w.id === d.warehouse_id)?.name || "";
                const conditionStr = d.condition === 'new' ? 'جديد' : 'مستعمل';
                const specsStr = (d.storage || d.ram) ? ` - ${d.storage || ''}/${d.ram || ''}` : '';
                imeiSelectHTML += `<option value="${d.id}" ${item.device_id === d.id ? 'selected' : ''}>${d.imei} (${conditionStr}${specsStr}) (${whName})</option>`;
            });
            imeiSelectHTML += `</select>`;
        }

        itemRow.innerHTML = `
            <div class="d-flex justify-content-between align-items-start">
                <div>
                    <h6 class="mb-0 fw-bold text-light">${item.name}</h6>
                    <small class="text-secondary">${item.price} ج.م</small>
                </div>
                <button class="btn btn-sm btn-outline-danger border-0 p-0" onclick="removeCartItem(${idx})">
                    <i class="bi bi-trash-fill fs-5"></i>
                </button>
            </div>
            <div class="row g-2 mt-2 align-items-center">
                <div class="col-7">
                    ${warehouseSelectHTML}
                </div>
                <div class="col-5">
                    <input type="number" class="form-control form-control-sm text-center" 
                           value="${item.quantity}" min="1" 
                           ${item.requires_imei ? 'disabled' : ''} 
                           oninput="updateCartItemQty(${idx}, this.value)">
                </div>
            </div>
            ${imeiSelectHTML}
        `;
        container.appendChild(itemRow);
    });
    
    calculateInvoiceTotals();
}

// حساب مجاميع الفاتورة

let currentGiftCardCode = '';
let currentGiftCardBalance = 0;
let storeEgpPer100Points = 5.0; // This should ideally be fetched, we will assume 5 or just pass it in HTML. Wait, we can fetch it or hardcode for now. Actually, we don't need to show the exact EGP discount dynamically before save, but it's better to. Let's just deduct it. For now, let's assume 100 points = 5 EGP.
// Wait, we can pass it from template.

function updateCustomerPoints() {
    const select = document.getElementById('customer-select');
    const selectedOption = select.options[select.selectedIndex];
    const points = selectedOption.getAttribute('data-points') || 0;
    
    const pointsDisplay = document.getElementById('customer-points-display');
    const pointsWrapper = document.getElementById('points-info-wrapper');
    const redeemInput = document.getElementById('points-redeem-input');
    
    if (points > 0) {
        pointsDisplay.textContent = points;
        pointsWrapper.classList.remove('d-none');
        redeemInput.max = points;
    } else {
        pointsWrapper.classList.add('d-none');
        redeemInput.value = 0;
        redeemInput.max = 0;
    }
    calculateInvoiceTotals();
}

function verifyGiftCard() {
    const code = document.getElementById('gift-card-input').value.trim();
    const msg = document.getElementById('gift-card-balance-msg');
    if (!code) {
        msg.textContent = '';
        msg.classList.add('d-none');
        currentGiftCardCode = '';
        currentGiftCardBalance = 0;
        calculateInvoiceTotals();
        return;
    }
    fetch("/pos/verify-gift-card/?code=" + encodeURIComponent(code))
        .then(response => response.json())
        .then(data => {
            msg.classList.remove('d-none', 'text-danger', 'text-success');
            if (data.valid) {
                msg.classList.add('text-success');
                msg.textContent = data.message;
                currentGiftCardCode = code;
                currentGiftCardBalance = data.balance;
            } else {
                msg.classList.add('text-danger');
                msg.textContent = data.message;
                currentGiftCardCode = '';
                currentGiftCardBalance = 0;
            }
            calculateInvoiceTotals();
        });
}

function calculateInvoiceTotals() {
    let total = 0;
    cart.forEach(item => {
        total += item.price * item.quantity;
    });

    const discountInput = document.getElementById("invoice-discount");
    const tradeInInput = document.getElementById("trade-in-value");
    
    const discount = parseFloat(discountInput.value) || 0;
    const tradeInValue = parseFloat(tradeInInput.value) || 0;
    
    let pointsRedeemed = parseInt(document.getElementById('points-redeem-input').value) || 0;
    // Assuming store_setting.egp_per_100_points is not easily accessible here without a template variable, 
    // we'll fetch it from a data attribute or assume 5 EGP for every 100 points as default.
    // Wait, let's look for a hidden input if we added one, otherwise use a placeholder (5 EGP per 100).
    // The backend handles the exact calculation, but for the frontend preview:
    let pointsDiscount = (pointsRedeemed / 100) * 5.0; 
    
    let netAmount = Math.max(0, (total - discount) - tradeInValue - pointsDiscount);
    
    let giftCardDeduction = 0;
    if (currentGiftCardBalance > 0) {
        giftCardDeduction = Math.min(currentGiftCardBalance, netAmount);
        netAmount -= giftCardDeduction;
    }

    document.getElementById("summary-total").textContent = `${total.toFixed(2)} ج.م`;
    document.getElementById("summary-discount").textContent = `${discount.toFixed(2)} ج.م`;
    document.getElementById("summary-trade-in").textContent = `${tradeInValue.toFixed(2)}- ج.م`;
    
    if (pointsDiscount > 0) {
        document.getElementById("summary-trade-in").innerHTML += `<br><small class="text-warning">نقاط الولاء: ${pointsDiscount.toFixed(2)}- ج.م</small>`;
    }
    if (giftCardDeduction > 0) {
        document.getElementById("summary-trade-in").innerHTML += `<br><small class="text-danger">بطاقة الهدية: ${giftCardDeduction.toFixed(2)}- ج.م</small>`;
    }
    
    document.getElementById("summary-net").textContent = `${netAmount.toFixed(2)} ج.م`;

    // إظهار قسم جهاز الاستبدال عند كتابة قيمة استبدال أكبر من صفر
    const tradeInSection = document.getElementById("trade-in-device-section");
    if (tradeInValue > 0) {
        tradeInSection.classList.remove("d-none");
    } else {
        tradeInSection.classList.add("d-none");
        document.getElementById("trade-in-device-select").value = "";
    }

    // تحديث طرق الدفع
    let payCash = parseFloat(document.getElementById("pay-cash").value) || 0;
    let payVisa = parseFloat(document.getElementById("pay-visa").value) || 0;
    let payWallet = parseFloat(document.getElementById("pay-wallet").value) || 0;

    const isCreditSale = document.getElementById("enable-credit-sale").checked;

    if (!isCreditSale) {
        // دفع كامل: منع تجاوز الصافي وضبط الكاش تلقائياً بناءً على ما أدخل في الفيزا والمحفظة
        if (payVisa > netAmount) payVisa = netAmount;
        if (payWallet > netAmount - payVisa) payWallet = netAmount - payVisa;
        
        document.getElementById("pay-visa").value = payVisa.toFixed(2);
        document.getElementById("pay-wallet").value = payWallet.toFixed(2);
        
        payCash = Math.max(0, netAmount - payVisa - payWallet);
        document.getElementById("pay-cash").value = payCash.toFixed(2);
        
        document.getElementById("summary-remaining-section").classList.add("d-none");
    } else {
        // بيع آجل: لا يتم ضبط الكاش تلقائياً، ويتم حساب المتبقي
        let totalPaid = payCash + payVisa + payWallet;
        // منع دفع مبلغ أكبر من الصافي في حالة الآجل أيضاً
        if (totalPaid > netAmount) {
            payCash = Math.max(0, netAmount - payVisa - payWallet);
            document.getElementById("pay-cash").value = payCash.toFixed(2);
            totalPaid = netAmount;
        }
        
        let remaining = Math.max(0, netAmount - totalPaid);
        document.getElementById("summary-remaining").textContent = `${remaining.toFixed(2)} ج.م`;
        document.getElementById("summary-remaining-section").classList.remove("d-none");
    }
}

function toggleCreditSale() {
    const isCredit = document.getElementById("enable-credit-sale").checked;
    const cashInput = document.getElementById("pay-cash");
    if (isCredit) {
        cashInput.removeAttribute("readonly");
    } else {
        cashInput.setAttribute("readonly", true);
    }
    calculateInvoiceTotals();
}

// إرسال الفاتورة والتسوية
function submitPOSInvoice() {
    if (cart.length === 0) {
        alert("السلة فارغة. يرجى إضافة عناصر أولاً.");
        return;
    }

    // التحقق من تحديد سيريالات الأجهزة المسيرنة
    for (let i = 0; i < cart.length; i++) {
        if (cart[i].requires_imei && !cart[i].device_id) {
            alert(`يرجى تحديد السيريال (IMEI) لـ: ${cart[i].name}`);
            return;
        }
    }

    const customerId = document.getElementById("customer-select").value;
    const discount = parseFloat(document.getElementById("invoice-discount").value) || 0;
    const tradeInValue = parseFloat(document.getElementById("trade-in-value").value) || 0;
    const tradedInDeviceId = document.getElementById("trade-in-device-select").value;

    if (tradeInValue > 0 && !tradedInDeviceId) {
        alert("يرجى اختيار جهاز الاستبدال من القائمة لربطه بالفاتورة.");
        return;
    }

    // حساب ومطابقة الدفع
    const payCash = parseFloat(document.getElementById("pay-cash").value) || 0;
    const payVisa = parseFloat(document.getElementById("pay-visa").value) || 0;
    const payWallet = parseFloat(document.getElementById("pay-wallet").value) || 0;
    const transactionId = document.getElementById("pay-transaction-id").value;

    const netAmount = parseFloat(document.getElementById("summary-net").textContent);
    const totalPaid = payCash + payVisa + payWallet;

    const isCreditSale = document.getElementById("enable-credit-sale").checked;
    
    if (totalPaid > netAmount + 0.02) {
        alert(`المجموع المدفوع (${totalPaid.toFixed(2)}) لا يمكن أن يكون أكبر من صافي الفاتورة (${netAmount.toFixed(2)})`);
        return;
    }
    
    if (!isCreditSale && totalPaid < netAmount - 0.02) {
        alert(`المجموع المدفوع (${totalPaid.toFixed(2)}) أقل من الصافي (${netAmount.toFixed(2)}). يرجى تفعيل (البيع بالآجل) أو تسديد كامل المبلغ.`);
        return;
    }

    const payload = {
        customer_id: parseInt(customerId),
        discount: discount,
        trade_in_value: tradeInValue,
        traded_in_device_id: tradedInDeviceId ? parseInt(tradedInDeviceId) : null,
        warranty_days: parseInt(document.getElementById("warranty-days").value) || 14,
        points_redeemed: parseInt(document.getElementById("points-redeem-input").value) || 0,
        gift_card_code: currentGiftCardCode,
        items: cart.map(item => ({
            product_id: item.product_id,
            warehouse_id: item.warehouse_id,
            device_id: item.device_id,
            quantity: item.quantity,
            unit_price: item.price
        })),
        payments: []
    };

    if (payCash > 0) payload.payments.push({ payment_method: 'cash', amount: payCash });
    if (payVisa > 0) payload.payments.push({ payment_method: 'visa', amount: payVisa, transaction_id: transactionId });
    if (payWallet > 0) payload.payments.push({ payment_method: 'wallet', amount: payWallet, transaction_id: transactionId });

    fetch("/pos/checkout/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrfToken()
        },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === "success") {
            alert("تم حفظ فاتورة البيع وخصم المخازن بنجاح!");
            // فتح نافذة طباعة وهمية للفاتورة
            printSimulatedReceipt(data.invoice_id);
            location.reload();
        } else {
            alert(`فشل الحفظ: ${data.error}`);
        }
    })
    .catch(err => {
        alert("حدث خطأ أثناء الاتصال بالخادم لحفظ الفاتورة.");
        console.error(err);
    });
}

function getCsrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || 
           document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1];
}

// محاكاة طباعة إيصال حراري حراري للـ POS
function printSimulatedReceipt(invoiceId) {
    const printWindow = window.open("", "_blank", "width=400,height=600");
    printWindow.document.write(`
        <html>
        <head>
            <title>طباعة فاتورة #${invoiceId}</title>
            <style>
                body { font-family: monospace; direction: rtl; text-align: center; padding: 20px; color: #000; }
                hr { border-top: 1px dashed #000; }
                .text-right { text-align: right; }
                .d-flex { display: flex; justify-content: space-between; }
            </style>
        </head>
        <body>
            <h3>EasyMB Store</h3>
            <p>مركز مبيعات وصيانة الهواتف الذكية</p>
            <hr>
            <p class="text-right">رقم الفاتورة: #${invoiceId}</p>
            <p class="text-right">التاريخ: ${new Date().toLocaleString()}</p>
            <hr>
            <h4>الأصناف</h4>
            <div class="text-right">
                ${cart.map(item => `
                    <div class="d-flex">
                        <span>${item.name} (${item.quantity}x)</span>
                        <span>${(item.price * item.quantity).toFixed(2)} ج.م</span>
                    </div>
                    ${item.imei ? `<small style="font-size:0.8rem;color:#555;">IMEI: ${item.imei}</small><br>` : ''}
                `).join('')}
            </div>
            <hr>
            <div class="d-flex"><strong>الصافي المطلوب:</strong> <strong>${document.getElementById("summary-net").textContent}</strong></div>
            <hr>
            <p>شكراً لزيارتكم! نرجو الاحتفاظ بالإيصال للضمان.</p>
            <script>window.onload = function() { window.print(); window.close(); }</script>
        </body>
        </html>
    `);
    printWindow.document.close();
}

// تحديث قائمة السيريالات عند التركيز عليها لضمان الحداثة التامة
function refreshIMEIDropdown(idx, selectEl) {
    const item = cart[idx];
    const currentValue = selectEl.value;
    
    // تصفية الأجهزة المتاحة لهذا المنتج
    const availableForProduct = allDevices.filter(d => d.product_id === item.product_id && (!item.condition || d.condition === item.condition));
    
    const warehouseOptions = Array.from(document.querySelectorAll("#warehouse-options-hidden option")).map(opt => ({
        id: parseInt(opt.value),
        name: opt.textContent
    }));

    // الاحتفاظ بالجهاز المحدد حالياً حتى لو تم حذفه من القائمة العامة (مثل تصفية الويب)
    let optionsHTML = `<option value="">-- اختر السيريال IMEI --</option>`;
    
    if (item.device_id && !availableForProduct.some(d => d.id === item.device_id)) {
        optionsHTML += `<option value="${item.device_id}" selected>${item.imei}</option>`;
    }
    
    availableForProduct.forEach(d => {
        const whName = warehouseOptions.find(w => w.id === d.warehouse_id)?.name || "";
        const conditionStr = d.condition === 'new' ? 'جديد' : 'مستعمل';
        const specsStr = (d.storage || d.ram) ? ` - ${d.storage || ''}/${d.ram || ''}` : '';
        optionsHTML += `<option value="${d.id}" ${parseInt(currentValue) === d.id ? 'selected' : ''}>${d.imei} (${conditionStr}${specsStr}) (${whName})</option>`;
    });
    
    selectEl.innerHTML = optionsHTML;
}

// سحب الكميات والأجهزة المتاحة لحظياً من السيرفر وتحديث الواجهة
function updateInventorySnapshot() {
    fetch('/pos/inventory-snapshot/')
        .then(response => {
            if (!response.ok) throw new Error("Network response was not ok");
            return response.json();
        })
        .then(data => {
            // تحديث المتغيرات العامة
            allDevices = data.devices;
            allStocks = data.stocks;
            
            // تحديث قيم "المتاح" على الكروت في شاشة المبيعات
            document.querySelectorAll('.available-qty-badge').forEach(badge => {
                const productId = parseInt(badge.getAttribute('data-product-id'));
                const condition = badge.getAttribute('data-condition') || null;
                const requiresImei = badge.getAttribute('data-requires-imei') === 'true';
                
                let qty = 0;
                if (requiresImei) {
                    qty = allDevices.filter(d => d.product_id === productId && (!condition || d.condition === condition)).length;
                } else {
                    qty = allStocks.filter(s => s.product_id === productId).reduce((sum, s) => sum + s.quantity, 0);
                }
                badge.textContent = `المتاح: ${qty}`;
            });
        })
        .catch(err => console.error("Error updating inventory snapshot:", err));
}

// بدء الفحص الدوري كل 5 ثوانٍ
setInterval(updateInventorySnapshot, 5000);

