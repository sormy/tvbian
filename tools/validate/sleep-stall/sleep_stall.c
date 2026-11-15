// SPDX-License-Identifier: GPL-2.0
/*
 * A device that hangs in its noirq suspend: the system never reaches sleep, and
 * only the watchdog brings it back. Loaded for a test, never shipped.
 */
#include <linux/delay.h>
#include <linux/module.h>
#include <linux/platform_device.h>

static unsigned int seconds = 200;
module_param(seconds, uint, 0644);
MODULE_PARM_DESC(seconds, "how long the noirq suspend hangs");

static int sleep_stall_suspend_noirq(struct device *dev)
{
	pr_emerg("sleep_stall: hanging %u s in noirq suspend\n", seconds);
	mdelay(seconds * 1000);
	return 0;
}

static const struct dev_pm_ops sleep_stall_pm_ops = {
	NOIRQ_SYSTEM_SLEEP_PM_OPS(sleep_stall_suspend_noirq, NULL)
};

static struct platform_driver sleep_stall_driver = {
	.driver = { .name = "sleep_stall", .pm = &sleep_stall_pm_ops },
};

static struct platform_device *sleep_stall_device;

static int __init sleep_stall_init(void)
{
	int ret = platform_driver_register(&sleep_stall_driver);

	if (ret)
		return ret;
	sleep_stall_device = platform_device_register_simple("sleep_stall", -1, NULL, 0);
	if (IS_ERR(sleep_stall_device)) {
		platform_driver_unregister(&sleep_stall_driver);
		return PTR_ERR(sleep_stall_device);
	}
	return 0;
}

static void __exit sleep_stall_exit(void)
{
	platform_device_unregister(sleep_stall_device);
	platform_driver_unregister(&sleep_stall_driver);
}

module_init(sleep_stall_init);
module_exit(sleep_stall_exit);
MODULE_DESCRIPTION("A hang in noirq suspend, for the watchdog to end");
MODULE_LICENSE("GPL");
