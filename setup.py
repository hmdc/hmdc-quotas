from distutils.core import setup

setup(author='Bradley Frank',
      author_email='bfrank@hmdc.harvard.edu',
      description='Tools for manipulating NetApp quotas using the NMSDK.',
      license='GPLv2',
      name='HMDCQuotas',
      packages=['hmdcquotas'],
      requires=['ConfigParser','hmdclogger','humanize','re','sys'],
      scripts=['scripts/quotasUtil.py'],
      url='https://github.com/hmdc/hmdc-quotas',
      version='1.2',
)
