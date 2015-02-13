from distutils.core import setup

<<<<<<< HEAD
setup(author='Bradley Frank',
      author_email='bfrank@hmdc.harvard.edu',
      description='Tools for manipulating NetApp quotas using the NMSDK.',
      license='GPLv2',
      name='HMDC Quotas',
      packages=['hmdcquotas'],
      requires=['ConfigParser','humanize','re','sys'],
      url='https://github.com/hmdc/hmdc-quotas',
      version='1.1',
=======
setup(name='Quotas',
      version='1.0',
      author='Bradley Frank',
      author_email='bfrank@hmdc.harvard.edu',
      url='https://github.com/hmdc/hmdc-logger',
      description='Manages NetApp ONTAP 8 quotas.',
      license='GPLv2',
      packages=['quotas'],
      requires=['hmdclogger','NaServer','ConfigParser','humanize','re','sys']
>>>>>>> 1f30ac8909a1ffa67280be90334e20f0a0b1418d
)
