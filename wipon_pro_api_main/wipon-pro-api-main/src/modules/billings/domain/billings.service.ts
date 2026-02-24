import { CACHE_MANAGER, Inject, Injectable, InternalServerErrorException, NotFoundException } from '@nestjs/common';
import { createCustomLogger } from '../../../common/logger/request-logger';
import { getConnection, getManager } from 'typeorm';
import { Response } from 'express';
import { AccountDao } from '../../../common/dao/account.dao';
import { FindUserByPhoneUseCase } from '../../users/domain/use-cases/find-user-by-phone.use-case';
import { LedgerDao } from '../../../common/dao/ledger.dao';
import { FindLedgersAccountsUseCase } from '../../accounts/domain/use-cases/find-ledgers-accounts.use-case';
import { AccountTransactionDao } from '../../../common/dao/account-transaction.dao';
import { Cache } from 'cache-manager';
import { buildXml } from '../../../common/helpers/xml';
import { InvoiceDao } from '../../../common/dao/invoice.dao';
import { UserDao } from '../../../common/dao/user.dao';
import { FindUserByIdUseCase } from '../../users/domain/use-cases/find-user-by-id.use-case';
import { SslService } from '../../../common/services/ssl/ssl.service';

@Injectable()
export class BillingsService {
  constructor(
    private readonly findUserByPhone: FindUserByPhoneUseCase,
    private readonly findLedgersAccounts: FindLedgersAccountsUseCase,
    private readonly findUserById: FindUserByIdUseCase,
    @Inject(CACHE_MANAGER) private cacheManager: Cache,
  ) {}

  async qiwiBilling(reqBody: any, ip: string, response: Response) {
    const entityManager = getManager();
    const logger = createCustomLogger('info', 'billing_qiwi');
    logger.info({
      message: `Request from IP ${ip}`,
      command: reqBody.command,
      txn_id: reqBody.txn_id,
      account: reqBody.account,
      sum: reqBody.sum,
    });

    response.setHeader('Content-Type', 'text/xml');

    if (reqBody.command == 'check') {
      const account = await entityManager.query(
        'select id from accounts where ledger_id = (select id from ledgers where user_id = (select id from users where phone_number=$1) or code=$2) and provider=$3',
        [`+7${reqBody.account}`, reqBody.account, 'qiwi'],
      );

      if (!account || !account.length) {
        const body = {
          osmp_txn_id: reqBody.txn_id,
          result: '5',
          comment: 'Account not found',
        };
        logger.warn({ message: 'response', body });
        return response.send(buildXml(body));
      }

      const accountData = await getConnection()
        .getRepository(AccountDao)
        .createQueryBuilder('account')
        .leftJoinAndSelect('account.ledger', 'ledger')
        .leftJoinAndSelect('ledger.user', 'user')
        .leftJoinAndSelect('user.store', 'store')
        .where('account.id = :accountId', { accountId: account[0].id })
        .getOne();

      const body = {
        osmp_txn_id: reqBody.txn_id,
        result: '0',
      };

      const bin = `${accountData?.ledger.user.store?.buisness_bin}<br>Ваш номер лицензии: ${accountData?.ledger.user.store?.license_number}`;
      const personalAccount = accountData?.ledger.user.store ? `<br>Ваш БИН: ${bin}` : '';

      logger.info({ message: 'response', body });
      const xmlBody = {
        ...body,
        comment: 'OK',
        fields: `Сообщаем, что с 1 января 2019 года в мобильном приложении Wipon Pro введены новые лицевые счета для оплаты доступа. Новый лицевой счет вы можете найти на главной странице мобильного приложения.<br><br>Ваш лицевой счет: ${accountData?.ledger.code}${personalAccount}`,
      };
      return response.send(buildXml(xmlBody));
    } else if (reqBody.command == 'pay') {
      let user = await this.findUserByPhone.handle(`+7${reqBody.account}`);
      let ledger: LedgerDao | undefined = user?.ledger;
      if (!user) {
        ledger = await LedgerDao.findOne({ where: { code: reqBody.account }, relations: ['user'] });
        user = ledger ? ledger.user : undefined;
      }

      const ledgerId = ledger ? ledger.id : null;
      const account = await this.findLedgersAccounts.handle(ledgerId, 'qiwi');
      if (!account) {
        const body = {
          osmp_txn_id: reqBody.txn_id,
          result: '5',
          comment: 'Account not found',
        };
        logger.warn({ message: 'response', body });
        return response.send(buildXml(body));
      }

      if (reqBody.sum <= 0) {
        const body = {
          osmp_txn_id: reqBody.txn_id,
          result: '241',
          comment: 'Сумма ',
        };
        logger.warn({ message: 'response', body });
        return response.send(buildXml(body));
      }

      const transactionsCount = await AccountTransactionDao.count({
        where: { txn_id: reqBody.txn_id, account_id: account.id },
      });

      if (!transactionsCount) {
        try {
          // $this->dispatch((new PaymentJob($user, $account, $request->input("sum"), $request->all(), $log))->onQueue("billing_pro"));
        } catch (e) {
          const body = {
            osmp_txn_id: reqBody.txn_id,
            sum: reqBody.sum,
            result: '8',
            exception_message: e,
          };
          logger.error({ message: 'response', body });
          const xmlBody = {
            osmp_txn_id: reqBody.txn_id,
            sum: reqBody.sum,
            result: '8',
            comment: 'Internal server error.',
          };
          return response.send(buildXml(xmlBody));
        }
      }

      const errorKey = `${account.provider}_error_${reqBody.txn_id}`;
      const transaction = await AccountTransactionDao.findOne({
        where: { accountId: account.id, txnId: reqBody.txn_id },
      });
      const paymentError = await this.cacheManager.get(errorKey);
      await this.cacheManager.del(errorKey);

      if (paymentError) {
        const body = {
          osmp_txn_id: reqBody.txn_id,
          sum: reqBody.sum,
          result: '8',
          exception_message: paymentError,
        };
        logger.error({ message: 'response', body });

        const xmlBody = {
          osmp_txn_id: reqBody.txn_id,
          sum: reqBody.sum,
          result: '8',
          comment: 'Internal server error.',
        };
        return response.send(buildXml(xmlBody));
      }

      const body: any = {
        osmp_txn_id: reqBody.txn_id,
        pvr_txn: transaction?.id,
        sum: transaction?.sum,
        result: '0',
      };
      logger.info({ message: 'response', body });
      body.comment = 'OK';
      return response.send(buildXml(body));
    } else {
      const body = {
        osmp_txn_id: reqBody.txn_id,
        result: '8',
        comment: 'Invalid command parameter',
      };
      logger.warn({ message: 'response', body });
      return response.send(buildXml(body));
    }
  }

  async kaspiBilling(reqBody: any, ip: string, response: Response) {
    const entityManager = getManager();
    const logger = createCustomLogger('info', 'billing_kaspi');
    logger.info({
      message: `Request from IP ${ip}`,
      command: reqBody.command,
      txn_id: reqBody.txn_id,
      account: reqBody.account,
      sum: reqBody.sum,
    });

    response.setHeader('Content-Type', 'text/xml');

    if (reqBody.command == 'check') {
      let qResult = await entityManager.query(
        'select accounts.balance as account_balance, invoices.status as invoice_status from accounts inner join ledgers on accounts.ledger_id = ledgers.id inner join invoices on ledgers.id = invoices.ledger_id where invoices.bill_id=$1 and invoices.provider=$2 and accounts.provider=$3',
        [reqBody.account, 'kaspi', 'kaspi'],
      );
      const body: any = {
        kaspi_txn_id: reqBody.txn_id,
      };

      if (!qResult || !qResult.length) {
        qResult = await entityManager.query(
          'select balance from accounts where ledger_id = (select id from ledgers where user_id = (select id from users where phone_number=$1) or code=$2) and provider=$3',
          [`+7${reqBody.account}`, reqBody.account, 'kaspi'],
        );

        if (qResult && qResult.length) {
          body.result = '0';
          body.sum = qResult[0].balance;
          body.comment = 'OK';
        } else {
          body.result = '1';
          body.sum = reqBody.sum;
          body.comment = 'Not found';
        }
      } else {
        body.sum = qResult[0].account_balance;
        if (qResult[0].invoice_status == 'paid') {
          body.result = '3';
          body.comment = 'Already paid';
        } else {
          body.result = '0';
          body.comment = 'OK';
        }
      }

      logger.info('response', body);
      return response.send(buildXml(body));
    } else if (reqBody.command == 'pay') {
      const qResult = await entityManager.query(
        'select accounts.id as account_id, ledgers.user_id as user_id, invoices.id as invoice_id from accounts inner join ledgers on accounts.ledger_id = ledgers.id inner join invoices on ledgers.id = invoices.ledger_id where invoices.bill_id=$1 and invoices.provider=$2 and accounts.provider=$3',
        [reqBody.account, 'kaspi', 'kaspi'],
      );

      let invoice: undefined | null | InvoiceDao;
      let user: null | undefined | UserDao;
      let account: null | undefined | AccountDao;

      if (qResult && qResult.length) {
        invoice = await InvoiceDao.findOne({ where: { id: qResult[0].invoice_id } });
        user = await entityManager.findOne(UserDao, { where: { id: qResult[0].user_id } });
        account = await entityManager.findOne(AccountDao, { where: { id: qResult[0].account_id } });
      } else {
        const accounts = await entityManager.query(
          'select id from accounts where ledger_id = (select id from ledgers where user_id = (select id from users where phone_number=$1) or code=$2) and provider=$3',
          [`+7${reqBody.account}`, reqBody.account, 'kaspi'],
        );
        if (accounts && accounts.length) {
          invoice = null;
          account = await entityManager
            .createQueryBuilder(AccountDao, 'account')
            .leftJoinAndSelect('account.ledger', 'ledger')
            .leftJoinAndSelect('ledger.user', 'user')
            .getOne();
          user = account?.ledger.user;
        } else {
          const body = {
            kaspi_txn_id: reqBody.txn_id,
            result: '3',
            sum: reqBody.sum,
            comment: 'Account not found',
          };
          logger.warn({ message: 'response', body });
          return response.send(buildXml(body));
        }
      }

      if ((invoice && reqBody.sum != invoice.amount) || reqBody.sum <= 0) {
        const body = {
          kaspi_txn_id: reqBody.txn_id,
          result: '4',
          sum: reqBody.sum,
          comment: 'Неверная сумма',
        };
        logger.warn({ message: 'response', body });
        return response.send(buildXml(body));
      }

      const transactionsCount = await AccountTransactionDao.count({
        where: { account_id: account?.id, txn_id: reqBody.txn_id },
      });

      const result = '0';

      if (!transactionsCount) {
        try {
          // $this->dispatch((new PaymentJob($user, $account, $request->input("sum"), $request->all(), $log))->onQueue("billing_pro"));
        } catch (e) {
          const body = {
            kaspi_txn_id: reqBody.txn_id,
            sum: reqBody.sum,
            result: '4',
            exception_message: e,
          };
          logger.error({ message: 'response', body });
          const xmlBody = {
            kaspi_txn_id: reqBody.txn_id,
            sum: reqBody.sum,
            result: '4',
            comment: 'Internal server error.',
          };
          return response.send(buildXml(xmlBody));
        }
      }

      const errorKey = `${account?.provider}_error_${reqBody.txn_id}`;
      const transaction = await AccountTransactionDao.findOne({
        where: { account_id: account?.id, txn_id: reqBody.txn_id },
      });
      const paymentError = await this.cacheManager.get(errorKey);
      await this.cacheManager.del(errorKey);

      if (paymentError) {
        const body = {
          kaspi_txn_id: reqBody.txn_id,
          sum: reqBody.sum,
          result: '4',
          exception_message: paymentError,
        };
        logger.error({ message: 'response', body });

        const xmlBody = {
          osmp_txn_id: reqBody.txn_id,
          sum: reqBody.sum,
          result: '8',
          comment: 'Internal server error.',
        };
        return response.send(buildXml(xmlBody));
      }

      if (invoice && result == '0') {
        invoice.status = 'paid';
        await InvoiceDao.save(invoice);
      }

      const body: any = {
        kaspi_txn_id: reqBody.txn_id,
        prv_txn: transaction?.id,
        sum: transaction?.sum,
        result,
      };
      logger.info({ message: 'response', body });
      body.comment = 'OK';
      return response.send(buildXml(body));
    } else {
      const body: any = {
        kaspi_txn_id: reqBody.txn_id,
        result: '1',
        comment: 'Invalid command parameter',
      };
      logger.warn({ message: 'response', body });
      return response.send(buildXml(body));
    }
  }

  async kassaBilling(reqBody: any, ip: string, response: Response) {
    const entityManager = getManager();
    const logger = createCustomLogger('info', 'billing_kassa24');
    logger.info({
      message: `Request from IP ${ip}`,
      action: reqBody.action,
      receipt: reqBody.receipt,
      number: reqBody.number,
      amount: reqBody.amount,
    });

    response.setHeader('Content-Type', 'text/xml');

    if (reqBody.action == 'check') {
      const accounts = await entityManager.query(
        'select id from accounts where ledger_id = (select id from ledgers where user_id = (select id from users where phone_number=$1) or code=$2) and provider=$3',
        [`+7${reqBody.number}`, reqBody.number, 'kassa24'],
      );
      const body: any = {
        code: '0',
        message: 'OK',
      };
      if (!accounts || !accounts.length) {
        body.code = '2';
        body.message = 'Account not found';
      }
      logger.info({ message: 'response', body });
      return response.send(buildXml(body));
    } else if (reqBody.action == 'payment') {
      let user = await this.findUserByPhone.handle(`+7${reqBody.number}`);
      let ledger: LedgerDao | undefined = user?.ledger;
      if (!user) {
        ledger = await LedgerDao.findOne({ where: { code: reqBody.number }, relations: ['user'] });
        user = ledger ? ledger.user : undefined;
      }

      const ledgerId = ledger ? ledger.id : null;
      const account = await this.findLedgersAccounts.handle(ledgerId, 'kassa24');
      if (!account) {
        const body = { code: '2', message: 'Account not found' };
        logger.warn({ message: 'response', body });
        return response.send(buildXml(body));
      }

      if (reqBody.amount <= 0) {
        const body = {
          receipt: reqBody.receipt,
          code: '3',
          message: 'Сумма слишком мала',
        };
        logger.warn({ message: 'response', body });
        return response.send(buildXml(body));
      }

      const transactionsCount = await AccountTransactionDao.count({
        where: { txn_id: reqBody.receipt, account_id: account.id },
      });

      if (!transactionsCount) {
        try {
          // $this->dispatch((new PaymentJob($user, $account, $request->input("sum"), $request->all(), $log))->onQueue("billing_pro"));
        } catch (e) {
          const body: any = {
            receipt: reqBody.receipt,
            amount: reqBody.amount,
            code: '10',
            date: new Date().toLocaleDateString('kk-KK', {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            }),
            exception_message: e,
          };
          logger.error({ message: 'response', body });
          delete body.exception_message;
          body.message = 'Internal server error.';
          return response.send(buildXml(body));
        }
      }

      const errorKey = `${account?.provider}_error_${reqBody.receipt}`;
      const transaction = await AccountTransactionDao.findOne({
        where: { account_id: account?.id, txn_id: reqBody.receipt },
      });
      const paymentError = await this.cacheManager.get(errorKey);
      await this.cacheManager.del(errorKey);

      if (paymentError) {
        const body: any = {
          receipt: reqBody.receipt,
          amount: reqBody.amount,
          code: '10',
          date: new Date().toLocaleDateString('kk-KK', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          }),
          exception_message: paymentError,
        };
        logger.error({ message: 'response', body });

        delete body.exception_message;
        body.message = 'Internal server error.';
        return response.send(buildXml(body));
      }

      const body = {
        receipt: reqBody.receipt,
        authcode: transaction?.id,
        amount: transaction?.sum,
        code: '0',
        date: new Date().toLocaleDateString('kk-KK', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        }),
        message: 'OK',
      };
      logger.info({ message: 'response', body });
      return response.send(buildXml(body));
    } else if (reqBody.action == 'status') {
      const transaction = await AccountTransactionDao.findOne({
        where: { provider: 'kassa24', txn_id: reqBody.receipt },
      });
      const body: any = {
        code: '6',
        message: 'Платёж не найден.',
      };
      if (transaction) {
        body.code = '0';
        body.authcode = transaction.id;
        body.message = 'OK';
        body.date = transaction.created_at;
      }
      return response.send(buildXml(body));
    } else if (reqBody.action == 'cancel') {
      return response.send(buildXml({ code: 9, message: 'Платёж не может быть отменён.' }));
    } else {
      const body = {
        receipt: reqBody.receipt,
        code: '1',
        message: 'Invalid action parameter',
      };
      logger.warn({ message: 'response', body });
      return response.send(buildXml(body));
    }
  }

  async wooppayBilling(reqBody: any, ip: string, invoiceId: string) {
    throw new InternalServerErrorException();
    // const entityManager = getManager();
    // const logger = createCustomLogger('info', 'billing_wooppay');
    // logger.info({ message: `Request from IP ${ip}`, invoiceId });
    // const invoice = await InvoiceDao.findOne({ where: { billId: invoiceId }, relations: ['ledger'] });
    // if (!invoice) {
    //   logger.warn({ message: 'response', invoiceId });
    //   throw new NotFoundException({ status: 'not found' });
    // }
    //
    // const response =
    // return 1;
  }

  //   $response = app('wooppay')->cashGetOperationData($invoice->operation_id);
  //   if ($response['error_code'] != 0 || ! isset($response['status']) || $response['status'] != 4) {
  //   $log->addWarning('response', $response);
  //   return response()->json([
  //                             'status' => 'not paid'
  //                           ], 200);
  // } // if operation

  async cyberplatBilling(reqBody: any, ip: string, response: Response) {
    throw new InternalServerErrorException();
    // TODO: Implement this with xml
    // const entityManager = getManager();
    // const logger = createCustomLogger('info', 'billing_cyberplat');
    // const params = JSON.parse(JSON.stringify(reqBody));
    // response.setHeader('Content-Type', 'text/xml');
    // logger.info({ message: `Request from IP ${ip}`, params });
    //
    // let isSigned = false;
    // logger.info({ message: `with sign ${httpBuildQuery(params)}` });
    //
    // if (params.sign) {
    //   const sign = hex2bin(params.sign);
    //   delete params.sign;
    //   logger.info({ message: `without sign ${httpBuildQuery(params)}` });
    //   if (this.sslService.checkSign(httpBuildQuery(params), sign, sslConfig.cyberplat.open)) {
    //     isSigned = true;
    //   }
    // }
    //
    // if (!isSigned) {
    //   const body = {
    //     code: 4,
    //     message: 'Ошибка проверки АСП.',
    //   };
    //   logger.warn({ message: 'response', body });
    // }
  }

  // private signXml(body: any, isUtf = true) {
  //
  // }
}

// TODO: 3. Learn Jobs and Queue and do it everywhere you left with commented block (JOB, QUEUE)
