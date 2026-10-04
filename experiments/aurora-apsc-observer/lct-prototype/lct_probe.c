// SPDX-License-Identifier: GPL-2.0-only
/*
 * PRIVATE, UNLOADED PROTOTYPE. The default build has no +0x38 MMIO read.
 * Do not deploy without the width/safety review described in DESIGN.md.
 */
#include <linux/atomic.h>
#include <linux/cpu.h>
#include <linux/cpufreq.h>
#include <linux/debugfs.h>
#include <linux/delay.h>
#include <linux/err.h>
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/kprobes.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/seq_file.h>
#include <linux/smp.h>
#include <linux/uaccess.h>
#include <linux/utsname.h>
#include <asm/arch_timer.h>
#include <asm/barrier.h>
#include <asm/sysreg.h>

/* Independent evidence must select a width and establish read safety. */
#define LCT_REVIEWED_WIDTH_BITS 0
#define LCT_READ_SAFETY_PROVEN 0
/* A separate future build may select known +0x20/+0x50 reads, never +0x38. */
#define LCT_COMMAND_ONLY_REVIEWED 0
#if LCT_REVIEWED_WIDTH_BITS != 0 && LCT_REVIEWED_WIDTH_BITS != 32 && LCT_REVIEWED_WIDTH_BITS != 64
#error "LCT_REVIEWED_WIDTH_BITS must be 0, 32 or 64"
#endif
#if LCT_READ_SAFETY_PROVEN != 0 && LCT_READ_SAFETY_PROVEN != 1
#error "LCT_READ_SAFETY_PROVEN must be 0 or 1"
#endif
#if LCT_COMMAND_ONLY_REVIEWED != 0 && LCT_COMMAND_ONLY_REVIEWED != 1
#error "LCT_COMMAND_ONLY_REVIEWED must be 0 or 1"
#endif
#if LCT_COMMAND_ONLY_REVIEWED && (LCT_REVIEWED_WIDTH_BITS || LCT_READ_SAFETY_PROVEN)
#error "Command-only and timestamp modes must be distinct builds"
#endif

#define LCT_RELEASE "7.1.12-ARCH-apsc-20261002-wfi-pcpm-abi3"
#define LCT_LAST_OFFSET 0x38
#define LCT_CMD_OFFSET 0x20
#define LCT_STATUS_OFFSET 0x50
#define LCT_BUSY BIT_ULL(31)
#define LCT_SAMPLES 64
#define LCT_SETS 2048

static const resource_size_t lct_expected_base[2] = {
	0x210e20000ULL, 0x211e20000ULL
};

/* This parameter is immutable after load and is not enough by itself. */
static bool allow_mmio;
module_param(allow_mmio, bool, 0400);
MODULE_PARM_DESC(allow_mmio, "Second, explicit gate after width and safety source review");

struct lct_read {
	u64 t0, t1, raw;
};

struct lct_sample {
	struct lct_read command, last, status;
	u32 seq, cpu, cluster, last_valid, committed;
	s32 error;
};

struct lct_set {
	u64 t0, t1, pre_command, submitted_command;
	u32 seq, entry_cpu, return_cpu, policy_cpu;
	u32 requested_index, requested_pstate;
	u32 committed;
	s32 error;
};

struct lct_return_data {
	u64 t0, pre_command, submitted_command;
	u32 seq, entry_cpu, policy_cpu, requested_index, requested_pstate;
};

static struct lct_sample samples[2][LCT_SAMPLES];
static struct lct_set sets[LCT_SETS];
static u32 sample_count[2];
static atomic_t set_attempts = ATOMIC_INIT(0);
static atomic_t set_overflow = ATOMIC_INIT(0);
static atomic_t set_inflight = ATOMIC_INIT(0);
static DEFINE_MUTEX(lct_lock);
static struct dentry *lct_dir;
static void __iomem *lct_base[2];
static bool capture_active, hardware_ready, kret_registered, sealed;
static int fatal_error;
static u32 counter_frequency;
static u64 sample_start_tick[2], sample_stop_tick[2];
static u32 set_attempts_at_start[2], set_attempts_at_stop[2];
static bool topology_before_ok[2], topology_after_ok[2];
static bool window_order_error[2];

/* Same heavy counter style as the retained counter-qualification helper. */
static notrace u64 lct_tick(void)
{
	u64 value;

	mb();
	value = arch_timer_read_cntpct_el0();
	arch_counter_enforce_ordering(value);
	mb();
	return value;
}

static int lct_last_read(void __iomem *base, u64 *value)
{
#if LCT_READ_SAFETY_PROVEN == 1 && LCT_REVIEWED_WIDTH_BITS == 32
	*value = readl(base + LCT_LAST_OFFSET);
	return 0;
#elif LCT_READ_SAFETY_PROVEN == 1 && LCT_REVIEWED_WIDTH_BITS == 64
	*value = readq(base + LCT_LAST_OFFSET);
	return 0;
#else
	/* No MMIO access, including no speculative fallback width. */
	return -EOPNOTSUPP;
#endif
}

/* Never let a signed atomic counter wrap into a valid array index. */
static int lct_reserve_set(void)
{
	int slot;

	for (;;) {
		slot = atomic_read(&set_attempts);
		if (slot >= LCT_SETS) {
			atomic_set(&set_overflow, 1);
			return -ENOSPC;
		}
		if (atomic_cmpxchg(&set_attempts, slot, slot + 1) == slot)
			return slot;
	}
}

static int lct_set_entry(struct kretprobe_instance *instance,
			 struct pt_regs *regs)
{
	struct lct_return_data *data = (void *)instance->data;
	struct cpufreq_policy *policy;
	int seq;

	/* Observe every call after registration, including pre-sample calls. */
	seq = lct_reserve_set();
	if (seq < 0)
		return 1;
	atomic_inc(&set_inflight);
	policy = (void *)regs->regs[0];
	data->seq = seq;
	data->entry_cpu = raw_smp_processor_id();
	data->policy_cpu = policy ? READ_ONCE(policy->cpu) : UINT_MAX;
	data->requested_index = regs->regs[2];
	data->requested_pstate = regs->regs[3];
	data->pre_command = regs->regs[4];
	data->submitted_command = regs->regs[5];
	data->t0 = lct_tick();
	return 0;
}

static int lct_set_return(struct kretprobe_instance *instance,
			  struct pt_regs *regs)
{
	const struct lct_return_data *data = (void *)instance->data;
	struct lct_set *set = &sets[data->seq];

	set->seq = data->seq;
	set->entry_cpu = data->entry_cpu;
	set->return_cpu = raw_smp_processor_id();
	set->policy_cpu = data->policy_cpu;
	set->requested_index = data->requested_index;
	set->requested_pstate = data->requested_pstate;
	set->pre_command = data->pre_command;
	set->submitted_command = data->submitted_command;
	set->t0 = data->t0;
	set->t1 = lct_tick();
	set->error = set->t1 < set->t0 ? -ERANGE : 0;
	smp_store_release(&set->committed, 1);
	atomic_dec(&set_inflight);
	return 0;
}

static struct kretprobe lct_set_probe = {
	.kp.symbol_name = "apple_apsc_observer_dvfs_write",
	.entry_handler = lct_set_entry,
	.handler = lct_set_return,
	.data_size = sizeof(struct lct_return_data),
	.maxactive = 128,
};

/* Caller holds the CPU-hotplug read lock for the full topology check. */
static int lct_check_policy_topology(void)
{
	struct cpufreq_policy *policy;
	int cpu, cluster, ret;

	if (num_online_cpus() != 8)
		return -ENODEV;
	for (cpu = 0; cpu < 8; cpu++) {
		if (!cpu_online(cpu))
			return -ENODEV;
		cluster = cpu < 4 ? 0 : 1;
		policy = cpufreq_cpu_get(cpu);
		if (!policy)
			return -ENODEV;
		ret = 0;
		if (cpumask_weight(policy->related_cpus) != 4 ||
		    !cpumask_test_cpu(cluster ? 4 : 0, policy->related_cpus) ||
		    !cpumask_test_cpu(cluster ? 5 : 1, policy->related_cpus) ||
		    !cpumask_test_cpu(cluster ? 6 : 2, policy->related_cpus) ||
		    !cpumask_test_cpu(cluster ? 7 : 3, policy->related_cpus))
			ret = -EINVAL;
		cpufreq_cpu_put(policy);
		if (ret)
			return ret;
	}
	return 0;
}

static int lct_check_and_map(void)
{
	struct device_node *cpu_node, *pd;
	struct resource res;
	struct cpufreq_policy *policy;
	int cpu, cluster, ret = -ENODEV;

	if (strcmp(utsname()->release, LCT_RELEASE) ||
	    !of_machine_is_compatible("apple,t8103") ||
	    num_possible_cpus() != 8)
		return -ENODEV;
	counter_frequency = read_sysreg(cntfrq_el0);
	if (counter_frequency != 24000000)
		return -ERANGE;
	cpus_read_lock();
	if (num_online_cpus() != 8)
		goto out;
	for (cpu = 0; cpu < 8; cpu++) {
		/* An early exit on any later CPU must not inherit prior success. */
		ret = -ENODEV;
		cluster = cpu < 4 ? 0 : 1;
		cpu_node = of_cpu_device_node_get(cpu);
		if (!cpu_node)
			goto out;
		pd = of_parse_phandle(cpu_node, "performance-domains", 0);
		of_node_put(cpu_node);
		if (!pd)
			goto out;
		ret = -ENODEV;
		if (!of_device_is_compatible(pd, "apple,t8103-cluster-cpufreq") ||
		    of_address_to_resource(pd, 0, &res) ||
		    res.start != lct_expected_base[cluster] ||
		    resource_size(&res) < LCT_STATUS_OFFSET + sizeof(u32)) {
			of_node_put(pd);
			goto out;
		}
		if (cpu == 0 || cpu == 4) {
			lct_base[cluster] = of_iomap(pd, 0);
			if (!lct_base[cluster]) {
				of_node_put(pd);
				ret = -ENOMEM;
				goto out;
			}
		}
		of_node_put(pd);
		policy = cpufreq_cpu_get(cpu);
		if (!policy) {
			ret = -ENODEV;
			goto out;
		}
		ret = 0;
		if (cpumask_weight(policy->related_cpus) != 4 ||
		    !cpumask_test_cpu(cluster ? 4 : 0, policy->related_cpus) ||
		    !cpumask_test_cpu(cluster ? 5 : 1, policy->related_cpus) ||
		    !cpumask_test_cpu(cluster ? 6 : 2, policy->related_cpus) ||
		    !cpumask_test_cpu(cluster ? 7 : 3, policy->related_cpus))
			ret = -EINVAL;
		cpufreq_cpu_put(policy);
		if (ret)
			goto out;
	}
	if (!lct_base[0] || !lct_base[1]) {
		ret = -ENODEV;
		goto out;
	}
	ret = 0;
out:
	cpus_read_unlock();
	if (ret)
		for (cluster = 0; cluster < 2; cluster++) {
			if (lct_base[cluster])
				iounmap(lct_base[cluster]);
			lct_base[cluster] = NULL;
		}
	return ret;
}

static void lct_bracket_command(void __iomem *base, struct lct_read *read)
{
	read->t0 = lct_tick();
	read->raw = readq(base + LCT_CMD_OFFSET);
	read->t1 = lct_tick();
}

static void lct_bracket_status(void __iomem *base, struct lct_read *read)
{
	read->t0 = lct_tick();
	read->raw = readl(base + LCT_STATUS_OFFSET);
	read->t1 = lct_tick();
}

static int lct_bracket_last(void __iomem *base, struct lct_read *read)
{
	int ret;

	read->t0 = lct_tick();
	ret = lct_last_read(base, &read->raw);
	read->t1 = lct_tick();
	return ret;
}

static bool lct_sample_order_ok(const struct lct_sample *sample,
				const struct lct_sample *previous,
				u64 window_start)
{
	u64 lower = previous ? previous->status.t1 : window_start;

	if (sample->command.t0 < lower ||
	    sample->command.t1 < sample->command.t0)
		return false;
	if (LCT_COMMAND_ONLY_REVIEWED)
		return sample->status.t0 >= sample->command.t1 &&
		       sample->status.t1 >= sample->status.t0;
	return sample->last_valid &&
	       sample->last.t0 >= sample->command.t1 &&
	       sample->last.t1 >= sample->last.t0 &&
	       sample->status.t0 >= sample->last.t1 &&
	       sample->status.t1 >= sample->status.t0;
}

static ssize_t lct_sample_write(struct file *file, const char __user *user,
				size_t count, loff_t *position)
{
	char input[32], extra;
	unsigned int cluster, n, i;
	int ret, cpu;
	struct lct_sample *sample;

	if (!count || count >= sizeof(input))
		return -EINVAL;
	if (copy_from_user(input, user, count))
		return -EFAULT;
	input[count] = '\0';
	if (sscanf(input, "%u %u %c", &cluster, &n, &extra) != 2 ||
	    cluster > 1 || !n || n > LCT_SAMPLES)
		return -EINVAL;
	if (!mutex_trylock(&lct_lock))
		return -EBUSY;
	if (!hardware_ready || sample_count[cluster] || fatal_error) {
		ret = -EOPNOTSUPP;
		goto out;
	}
	if (READ_ONCE(lct_set_probe.nmissed) || atomic_read(&set_overflow) ||
	    atomic_read(&set_inflight)) {
		ret = -EOVERFLOW;
		goto out;
	}
	cpus_read_lock();
	ret = lct_check_policy_topology();
	if (ret) {
		fatal_error = ret;
		goto out_cpus;
	}
	topology_before_ok[cluster] = true;
	cpu = get_cpu();
	if (read_sysreg(cntfrq_el0) != counter_frequency) {
		put_cpu();
		fatal_error = -ERANGE;
		ret = fatal_error;
		goto out_cpus;
	}
	set_attempts_at_start[cluster] = atomic_read(&set_attempts);
	sample_start_tick[cluster] = lct_tick();
	smp_store_release(&capture_active, true);
	for (i = 0; i < n; i++) {
		sample = &samples[cluster][i];
		sample->seq = i;
		sample->cpu = cpu;
		sample->cluster = cluster;
		lct_bracket_command(lct_base[cluster], &sample->command);
		if (LCT_COMMAND_ONLY_REVIEWED) {
			/* The +0x38 address is never accessed in this mode. */
			sample->last_valid = 0;
			sample->error = 0;
		} else {
			sample->error = lct_bracket_last(lct_base[cluster], &sample->last);
			sample->last_valid = !sample->error;
		}
		if (!sample->error)
			lct_bracket_status(lct_base[cluster], &sample->status);
		if (!sample->error &&
		    !lct_sample_order_ok(sample,
					 i ? &samples[cluster][i - 1] : NULL,
					 sample_start_tick[cluster]))
			sample->error = -ERANGE;
		smp_store_release(&sample->committed, 1);
		sample_count[cluster]++;
		if (sample->error) {
			fatal_error = sample->error;
			break;
		}
		udelay(2);
	}
	smp_store_release(&capture_active, false);
	sample_stop_tick[cluster] = lct_tick();
	set_attempts_at_stop[cluster] = atomic_read(&set_attempts);
	if (sample_stop_tick[cluster] < sample_start_tick[cluster] ||
	    read_sysreg(cntfrq_el0) != counter_frequency) {
		window_order_error[cluster] = true;
		fatal_error = -ERANGE;
	}
	for (i = 0; i < sample_count[cluster]; i++)
		if (!samples[cluster][i].error &&
		    samples[cluster][i].status.t1 > sample_stop_tick[cluster]) {
			window_order_error[cluster] = true;
			fatal_error = -ERANGE;
		}
	put_cpu();
	ret = lct_check_policy_topology();
	if (ret)
		fatal_error = ret;
	else
		topology_after_ok[cluster] = true;
	if (num_online_cpus() != 8)
		fatal_error = -ENODEV;
	cpus_read_unlock();
	if (READ_ONCE(lct_set_probe.nmissed) || atomic_read(&set_overflow))
		fatal_error = -EOVERFLOW;
	ret = fatal_error ? fatal_error : count;
	goto out;
out_cpus:
	cpus_read_unlock();
out:
	mutex_unlock(&lct_lock);
	return ret;
}

static int lct_status_show(struct seq_file *seq, void *ignored)
{
	u32 attempted, committed = 0, i;

	mutex_lock(&lct_lock);
	attempted = atomic_read(&set_attempts);
	for (i = 0; i < min_t(u32, attempted, LCT_SETS); i++)
		committed += !!smp_load_acquire(&sets[i].committed);
	seq_printf(seq, "release=%s\nwidth_bits=%d\nread_safety_proven=%d\ncommand_only_reviewed=%d\nallow_mmio=%d\nhardware_ready=%d\nsealed=%d\ncntfrq=%u\n",
		   LCT_RELEASE, LCT_REVIEWED_WIDTH_BITS,
		   LCT_READ_SAFETY_PROVEN, LCT_COMMAND_ONLY_REVIEWED,
		   allow_mmio, hardware_ready, sealed,
		   counter_frequency);
	seq_printf(seq, "sample0=%u\nsample1=%u\nsample0_start_tick=%llu\nsample0_stop_tick=%llu\nsample1_start_tick=%llu\nsample1_stop_tick=%llu\nset0_start_seq=%u\nset0_stop_seq=%u\nset1_start_seq=%u\nset1_stop_seq=%u\n",
		   sample_count[0], sample_count[1],
		   sample_start_tick[0], sample_stop_tick[0],
		   sample_start_tick[1], sample_stop_tick[1],
		   set_attempts_at_start[0], set_attempts_at_stop[0],
		   set_attempts_at_start[1], set_attempts_at_stop[1]);
	seq_printf(seq, "topology0_before_ok=%u\ntopology0_after_ok=%u\ntopology1_before_ok=%u\ntopology1_after_ok=%u\n",
		   topology_before_ok[0], topology_after_ok[0],
		   topology_before_ok[1], topology_after_ok[1]);
	seq_printf(seq, "window0_order_error=%u\nwindow1_order_error=%u\n",
		   window_order_error[0], window_order_error[1]);
	seq_printf(seq, "set_attempts=%u\nset_committed=%u\nset_missing_commit=%u\nset_inflight=%d\nset_overflow=%d\nkret_missed=%d\npre_registration_coverage_unknown=1\nactual_writer_cpu_qualified=0\nfatal_error=%d\n",
		   attempted, committed,
		   min_t(u32, attempted, LCT_SETS) - committed,
		   atomic_read(&set_inflight),
		   atomic_read(&set_overflow), READ_ONCE(lct_set_probe.nmissed),
		   fatal_error);
	mutex_unlock(&lct_lock);
	return 0;
}

static int lct_status_open(struct inode *inode, struct file *file)
{
	return single_open(file, lct_status_show, NULL);
}

static int lct_samples_show(struct seq_file *seq, void *ignored)
{
	const struct lct_sample *s;
	u32 i;
	int cluster;

	mutex_lock(&lct_lock);
	if (!sealed) {
		mutex_unlock(&lct_lock);
		return -EAGAIN;
	}
	seq_puts(seq, "cluster,seq,cpu,cmd_t0,cmd_t1,cmd,last_valid,last_t0,last_t1,last_raw,status_t0,status_t1,status,error,committed\n");
	for (cluster = 0; cluster < 2; cluster++)
		for (i = 0; i < sample_count[cluster]; i++) {
			s = &samples[cluster][i];
			seq_printf(seq, "%u,%u,%u,%llu,%llu,0x%016llx,%u,%llu,%llu,0x%016llx,%llu,%llu,0x%08llx,%d,%u\n",
				   s->cluster, s->seq, s->cpu,
				   s->command.t0, s->command.t1,
				   s->command.raw, s->last_valid, s->last.t0,
				   s->last.t1, s->last.raw,
				   s->status.t0, s->status.t1,
				   s->status.raw, s->error,
				   smp_load_acquire(&s->committed));
		}
	mutex_unlock(&lct_lock);
	return 0;
}

static int lct_samples_open(struct inode *inode, struct file *file)
{
	return single_open(file, lct_samples_show, NULL);
}

static const struct file_operations lct_samples_fops = {
	.owner = THIS_MODULE,
	.open = lct_samples_open,
	.read = seq_read,
	.llseek = seq_lseek,
	.release = single_release,
};

static int lct_sets_show(struct seq_file *seq, void *ignored)
{
	const struct lct_set *s;
	u32 attempted, i;

	mutex_lock(&lct_lock);
	if (!sealed) {
		mutex_unlock(&lct_lock);
		return -EAGAIN;
	}
	attempted = min_t(u32, atomic_read(&set_attempts), LCT_SETS);
	seq_puts(seq, "seq,entry_cpu,return_cpu,policy_cpu,requested_index,requested_pstate,pre_command,submitted_command,t0,t1,error,committed\n");
	for (i = 0; i < attempted; i++) {
		s = &sets[i];
		seq_printf(seq, "%u,%u,%u,%u,%u,%u,0x%016llx,0x%016llx,%llu,%llu,%d,%u\n",
			   i, s->entry_cpu, s->return_cpu, s->policy_cpu,
			   s->requested_index, s->requested_pstate,
			   s->pre_command, s->submitted_command,
			   s->t0, s->t1, s->error,
			   smp_load_acquire(&s->committed));
	}
	mutex_unlock(&lct_lock);
	return 0;
}

static int lct_sets_open(struct inode *inode, struct file *file)
{
	return single_open(file, lct_sets_show, NULL);
}

static const struct file_operations lct_sets_fops = {
	.owner = THIS_MODULE,
	.open = lct_sets_open,
	.read = seq_read,
	.llseek = seq_lseek,
	.release = single_release,
};

static const struct file_operations lct_status_fops = {
	.owner = THIS_MODULE,
	.open = lct_status_open,
	.read = seq_read,
	.llseek = seq_lseek,
	.release = single_release,
};

static const struct file_operations lct_sample_fops = {
	.owner = THIS_MODULE,
	.write = lct_sample_write,
	.llseek = noop_llseek,
};

static ssize_t lct_seal_write(struct file *file, const char __user *user,
			      size_t count, loff_t *position)
{
	char input[8];

	if (!count || count >= sizeof(input))
		return -EINVAL;
	if (copy_from_user(input, user, count))
		return -EFAULT;
	input[count] = '\0';
	if (strcmp(input, "seal") && strcmp(input, "seal\n"))
		return -EINVAL;
	mutex_lock(&lct_lock);
	if (!hardware_ready || sealed) {
		mutex_unlock(&lct_lock);
		return -EOPNOTSUPP;
	}
	hardware_ready = false;
	smp_store_release(&capture_active, false);
	unregister_kretprobe(&lct_set_probe);
	kret_registered = false;
	if (atomic_read(&set_inflight) ||
	    READ_ONCE(lct_set_probe.nmissed) || atomic_read(&set_overflow))
		fatal_error = -EOVERFLOW;
	sealed = true;
	mutex_unlock(&lct_lock);
	return count;
}

static const struct file_operations lct_seal_fops = {
	.owner = THIS_MODULE,
	.write = lct_seal_write,
	.llseek = noop_llseek,
};

static int __init lct_init(void)
{
	int ret;

	lct_dir = debugfs_create_dir("apple_lct_private", NULL);
	if (IS_ERR_OR_NULL(lct_dir))
		return -ENODEV;
	if (IS_ERR_OR_NULL(debugfs_create_file("status", 0400, lct_dir,
					    NULL, &lct_status_fops)))
		goto fail;
	if (IS_ERR_OR_NULL(debugfs_create_file("sample", 0200, lct_dir,
					    NULL, &lct_sample_fops)))
		goto fail;
	if (IS_ERR_OR_NULL(debugfs_create_file("seal", 0200, lct_dir,
					    NULL, &lct_seal_fops)))
		goto fail;
	if (IS_ERR_OR_NULL(debugfs_create_file("samples.csv", 0400, lct_dir,
					    NULL, &lct_samples_fops)))
		goto fail;
	if (IS_ERR_OR_NULL(debugfs_create_file("sets.csv", 0400, lct_dir,
					    NULL, &lct_sets_fops)))
		goto fail;
	if (!allow_mmio ||
	    (!LCT_COMMAND_ONLY_REVIEWED &&
	     (!LCT_REVIEWED_WIDTH_BITS || !LCT_READ_SAFETY_PROVEN)))
		return 0;
	ret = lct_check_and_map();
	if (ret)
		goto fail;
	ret = register_kretprobe(&lct_set_probe);
	if (ret)
		goto unmap;
	kret_registered = true;
	hardware_ready = true;
	return 0;
unmap:
	iounmap(lct_base[0]);
	iounmap(lct_base[1]);
fail:
	debugfs_remove_recursive(lct_dir);
	return -ENODEV;
}

static void __exit lct_exit(void)
{
	debugfs_remove_recursive(lct_dir);
	mutex_lock(&lct_lock);
	hardware_ready = false;
	smp_store_release(&capture_active, false);
	if (kret_registered)
		unregister_kretprobe(&lct_set_probe);
	if (lct_base[0])
		iounmap(lct_base[0]);
	if (lct_base[1])
		iounmap(lct_base[1]);
	mutex_unlock(&lct_lock);
}

module_init(lct_init);
module_exit(lct_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Private fail-closed T8103 LAST_CHG_TIME calibration prototype");
