import {
  Column,
  CreateDateColumn,
  DeleteDateColumn,
  Entity,
  JoinColumn,
  ManyToOne,
  OneToMany,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { LedgerDao } from './ledger.dao';
import { AccountTransactionDao } from './account-transaction.dao';

@Entity('accounts')
export class AccountDao {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ type: 'integer', nullable: true, name: 'user_id' })
  user_id: number | null;

  @Column()
  provider: string;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updated_at: Date;

  @DeleteDateColumn({ name: 'deleted_at' })
  deleted_at: Date;

  @Column({ type: 'numeric', precision: 10, scale: 2 })
  balance: number;

  @Column({ name: 'ledger_id' })
  ledger_id: number;

  @ManyToOne(() => LedgerDao, (ledger) => ledger.accounts)
  @JoinColumn({ name: 'ledger_id' })
  ledger: LedgerDao;

  @OneToMany(() => AccountTransactionDao, (accountTransaction) => accountTransaction.account)
  transactions: AccountTransactionDao[];
}
