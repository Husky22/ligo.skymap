#
# Copyright (C) 2013-2018  Leo Singer
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
"""
Create summary plots for sky maps of found injections, optionally binned
cumulatively by false alarm rate or SNR.
"""

from argparse import FileType
from distutils.dir_util import mkpath
import os

from . import ArgumentParser


def parser():
    parser = ArgumentParser()
    parser.add_argument('--cumulative', action='store_true')
    parser.add_argument('--normed', action='store_true')
    parser.add_argument(
        '--group-by', choices=('far', 'snr'), metavar='far|snr',
        help='Group plots by false alarm rate (FAR) or ' +
        'signal to noise ratio (SNR)')
    parser.add_argument(
        '--pp-confidence-interval', type=float, metavar='PCT',
        default=95, help='If all inputs files have the same number of '
        'samples, overlay binomial confidence bands for this percentage on '
        'the P--P plot')
    parser.add_argument(
        '--format', default='pdf', help='Matplotlib format')
    parser.add_argument(
        'input', type=FileType('rb'), nargs='+',
        help='Name of input file generated by ligo-skymap-stats')
    parser.add_argument(
        '--output', '-o', default='.', help='output directory')
    return parser


def main(args=None):
    opts = parser().parse_args(args)

    # Imports.
    from astropy.table import Table
    import matplotlib
    matplotlib.use('agg')
    from matplotlib import pyplot as plt
    from matplotlib import rcParams
    import numpy as np
    from tqdm import tqdm
    from .. import plot  # noqa

    # Read in all of the datasets listed as positional command line arguments.
    datasets = [Table.read(file, format='ascii') for file in opts.input]

    # Determine plot colors and labels
    filenames = [file.name for file in opts.input]
    labels = [os.path.splitext(os.path.basename(f))[0] for f in filenames]
    if rcParams['text.usetex']:
        labels = [r'\verb/' + label + '/' for label in labels]
    rcParams['savefig.format'] = opts.format

    # Normalize column names
    for dataset in datasets:
        if 'p_value' in dataset.colnames:
            dataset.rename_column('p_value', 'searched_prob')

    if opts.group_by == 'far':

        def key_func(table):
            return -np.log10(table['far'])

        def key_to_dir(key):
            return 'far_1e{}'.format(-key)

        def key_to_title(key):
            return r'$\mathrm{{FAR}} \leq 10^{{{}}}$ Hz'.format(-key)

    elif opts.group_by == 'snr':

        def key_func(table):
            return table['snr']

        def key_to_dir(key):
            return 'snr_{}'.format(key)

        def key_to_title(key):
            return r'$\mathrm{{SNR}} \geq {}$'.format(key)

    else:

        def key_func(table):
            return np.zeros(len(table))

        def key_to_dir(key):
            return '.'

        def key_to_title(key):
            return 'All events'

    if opts.group_by is not None:
        missing = [filename for filename, dataset in zip(filenames, datasets)
                   if opts.group_by not in dataset.colnames]
        if missing:
            raise RuntimeError(
                'The following files had no "'
                + opts.group_by + '" column: ' + ' '.join(missing))

    for dataset in datasets:
        dataset['key'] = key_func(dataset)

    if opts.group_by is not None:
        invalid = [filename for filename, dataset in zip(filenames, datasets)
                   if not np.all(np.isfinite(dataset['key']))]
        if invalid:
            raise RuntimeError(
                'The following files had invalid values in the "'
                + opts.group_by + '" column: ' + ' '.join(invalid))

    keys = np.concatenate([dataset['key'] for dataset in datasets])

    histlabel = []
    if opts.cumulative:
        histlabel.append('cumulative')
    if opts.normed:
        histlabel.append('fraction')
    else:
        histlabel.append('number')
    histlabel.append('of injections')
    histlabel = ' '.join(histlabel)

    pp_plot_settings = [
        ['', 'searched posterior mass'],
        ['_dist', 'distance CDF at true distance'],
        ['_vol', 'searched volumetric probability']]
    hist_settings = [
        ['searched_area', 'searched_area (deg$^2$)'],
        ['searched_vol', 'searched volume (Mpc$^3$)'],
        ['offset', 'angle from true location and mode of posterior (deg)'],
        ['runtime', 'run time (s)']]

    keys = range(*np.floor([keys.min(), keys.max()+1]).astype(int))
    total = len(keys) * (len(pp_plot_settings) + len(hist_settings))
    with tqdm(total=total) as progress:
        for key in keys:
            filtered = [d[d['key'] >= key] for d in datasets]
            title = key_to_title(key)
            nsamples = {len(d) for d in filtered}
            if len(nsamples) == 1:
                nsamples, = nsamples
                title += ' ({} events)'.format(nsamples)
            else:
                nsamples = None

            subdir = os.path.join(opts.output, key_to_dir(key))
            mkpath(subdir)

            # Make several different kinds of P-P plots
            for suffix, xlabel in pp_plot_settings:
                colname = 'searched_prob' + suffix
                fig = plt.figure(figsize=(6, 6))
                ax = fig.add_subplot(111, projection='pp_plot')
                fig.subplots_adjust(bottom=0.15)
                ax.set_xlabel(xlabel)
                ax.set_ylabel('cumulative fraction of injections')
                ax.set_title(title)
                ax.add_series(*[d.columns.get(colname, []) for d in filtered])
                ax.add_diagonal()
                if nsamples:
                    ax.add_confidence_band(
                        nsamples, 0.01 * opts.pp_confidence_interval)
                ax.grid()
                if len(filtered) > 1:
                    ax.legend(labels, loc='lower right')
                fig.savefig(os.path.join(subdir, colname))
                plt.close()
                progress.update()

            # Make several different kinds of histograms
            for colname, xlabel in hist_settings:
                fig = plt.figure(figsize=(6, 4.5))
                ax = fig.add_subplot(111)
                fig.subplots_adjust(bottom=0.15)
                ax.set_xscale('log')
                ax.set_xlabel(xlabel)
                ax.set_ylabel(histlabel)
                ax.set_title(title)
                values = np.concatenate(
                    [d.columns.get(colname, []) for d in filtered])
                if len(values) > 0:
                    bins = np.logspace(np.log10(np.min(values)),
                                       np.log10(np.max(values)),
                                       1000 if opts.cumulative else 20)
                    ax.hist([d.columns.get(colname, []) for d in filtered],
                            cumulative=opts.cumulative, density=opts.normed,
                            histtype='step', bins=bins)
                ax.grid()
                ax.legend(labels, loc='upper left')
                fig.savefig(os.path.join(subdir, colname + '_hist'))
                plt.close()
                progress.update()
